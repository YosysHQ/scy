import asyncio
import copy
import os
import json
import re
from scy.scy_task_tree import TaskTree
from scy.scy_config_parser import SCYConfig
from scy.scy_sby_bridge import SBYBridge

import yosys_mau.task_loop.job_server as job

async def runner(client: job.Client, exe_args: "list[str]", workdir: str):
    lease = client.request_lease()
    await lease

    print(f'Running "{" ".join(exe_args)}"')
    coro = await asyncio.create_subprocess_exec(
        *exe_args, cwd=workdir, 
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    await coro.wait()

    del lease
    return coro

def parse_common_sby(common_task: TaskTree, sbycfg: SBYBridge, scycfg: SCYConfig):
    assert common_task.is_common, "expected tree root to be common.sby generation"

    # preparse tree to extract cell generation
    add_cells: "dict[int, dict[str]]" = {}
    enable_cells: "dict[str, dict[str, str | bool]]" = {}
    def add_enable_cell(hdlname: str, stmt: str):
        enable_cells.setdefault(hdlname, {"disable": "1'b0"})
        enable_cells[hdlname][f"does_{stmt}"] = True

    for task in common_task.traverse():
        if task.stmt == "add":
            if task.name not in ["assert", "assume", "live", "fair", "cover"]:
                raise NotImplementedError(f"cell type {task.name!r} on line {task.line}")
            add_cells[task.line] = {"type": task.name}
            add_cells[task.line].update(task.get_asgmt())
        elif task.stmt in ["enable", "disable"]:
            add_enable_cell(task.name, task.stmt)
        elif task.body:
            for line in task.body.split('\n'):
                try:
                    stmt, hdlname = line.split()
                except ValueError:
                    continue
                if stmt in ["enable", "disable"]:
                    add_enable_cell(hdlname, stmt)

    # add cells to sby script
    add_log = None
    for (line, cell) in add_cells.items():
        sbycfg.script.extend([f"add -{cell['type']} {cell['lhs']} # line {line}",
                            f"setattr -set scy_line {line}  w:{cell['lhs']} %co c:$auto$add* %i"])
    for hdlname in enable_cells.keys():
        select = f"w:*:*_EN c:{hdlname} %ci:+[EN] %i"
        sbycfg.script.append(f"setattr -set scy_line 0 -set hdlname:{hdlname} 1 {select}")
    if add_cells or enable_cells:
        add_log = "add_cells.log"
        sbycfg.script.append(f"tee -o {add_log} printattrs a:scy_line")
        add_log = os.path.join(scycfg.args.workdir, "common", "src", add_log)

    return (add_log, add_cells, enable_cells)

def gen_sby(task: TaskTree, sbycfg: SBYBridge, scycfg: SCYConfig,
            add_cells: "dict[int, dict[str]]", 
            enable_cells: "dict[str, dict[str, str | bool]]"):

    sbycfg = copy.deepcopy(sbycfg)

    if not task.is_root and not task.parent.is_common:
        # child nodes depend on parent
        parent = task.parent
        parent_trace = os.path.join(parent.get_dir(),
                                 "engine_0",
                                 f"trace0.{scycfg.options.trace_ext}")
        traces = [os.path.join(parent.get_dir(),
                               "src", 
                               trace.split()[0]) for trace in task.traces[:-1]]
        sbycfg.files.extend(traces + [f"{parent.tracestr}.{scycfg.options.trace_ext} {parent_trace}"])

    # configure additional cells
    pre_sim_commands = []
    post_sim_commands = []
    for cell in add_cells.values():
        en_sig = '1' if cell["cell"] in task.enable_cells else '0'
        pre_sim_commands.append(f"connect -port {cell['cell']} \\EN 1'b{en_sig}")
    for hdlname in enable_cells.keys():
        task_cell = task.enable_cells.get(hdlname, None)
        if task.has_local_enable_cells:
            for line in task.body.split('\n'):
                if hdlname in line:
                    task_cell = enable_cells[hdlname].copy()
                    task_cell["status"] = line.split()[0]
                    break
        if task_cell:
            status = task_cell["status"]
            pre_sim_commands.append(f"connect -port {hdlname} \\EN {task_cell[status]}")
            if status == "enable":
                post_sim_commands.append(f"chformal -skip 1 c:{hdlname}")
    sbycfg.script.extend(pre_sim_commands)

    # replay prior traces and enable only relevant cover
    traces_script = []
    for trace in task.traces:
        if scycfg.options.replay_vcd:
            trace_scope = f" -scope {scycfg.options.design_scope}" 
        else:
            trace_scope = ""
        traces_script.append(f"sim -w -r {trace}{trace_scope}")
    if task.stmt == "cover":
        traces_script.append(f"delete t:$cover c:{task.name} %d")
        sbycfg.script.extend(traces_script)
    else:
        raise NotImplementedError(task.stmt)
    sbycfg.script.extend(post_sim_commands)

    return sbycfg

def gen_traces(task: TaskTree) -> "list[str]":
    # reversing trace order means that the most recent trace will be first
    task.traces.reverse()
    traces = []
    last_trace = True
    for trace in task.traces:
        split_trace = trace.split(maxsplit=1)
        if len(split_trace) == 2:
            trace, append = split_trace
            append = int(append.split()[-1])
        else:
            append = 0
        if last_trace:
            last_trace = False
            trace_path = os.path.join(task.get_dir(),
                                    "engine_0",
                                    "trace0.yw")
        else:
            # using sim -w appears to combine the final step of one trace with the first step of the next
            # we emulate this by telling yosys-witness to skip one extra cycle than we told sim
            append -= 1
            trace_path = os.path.join(task.get_dir(),
                                    "src", 
                                    trace)
        traces.append(f"{trace_path} -p {append}")

    # we now need to flip the order back to the expected order
    task.traces.reverse()
    traces.reverse()
    return traces

class TaskRunner():
    def __init__(self, sbycfg: SBYBridge, scycfg: SCYConfig, client: job.Client):
        self.sbycfg = sbycfg
        self.scycfg = scycfg
        self.client = client
        self.add_cells: "dict[int, dict[str]]" = {}
        self.enable_cells: "dict[str, dict[str, str | bool]]" = {}
        self.task_steps: "dict[str, int]" = {}

    async def run_tree(self):
        p = []
        common_task = self.scycfg.sequence
        workdir = self.scycfg.args.workdir

        (add_log, self.add_cells, self.enable_cells) = parse_common_sby(common_task, self.sbycfg, self.scycfg)

        # use sby to prepare input
        print(f"Preparing input files")
        task_sby = os.path.join(f"{workdir}", 
                                f"common.sby")

        with open(task_sby, 'w') as sbyfile:
            self.sbycfg.dump_common(sbyfile)

        sby_args = ["sby", "common.sby"]
        p.append(await runner(self.client, sby_args, workdir))

        if self.scycfg.options.replay_vcd and not self.scycfg.options.design_scope:
            # load top level design name back from generated model
            design_json = os.path.join(workdir, "common", "model", "design.json")
            with open(design_json, 'r') as f:
                design = json.load(f)

            assert len(design["modules"]) == 1, ("expected one top level module, " 
                                                "try setting the 'design_scope' option")
            self.scycfg.options.design_scope = design["modules"][0]["name"]

        if add_log:
            # load back added cells
            with open(add_log, 'r') as f:
                cell_dump = f.read()
                cell_regex = r"(?P<cell>\S+)(?P<body>(?:\n  (?:.*))*)"
                for cell_m in re.finditer(cell_regex, cell_dump):
                    property_regex = r"  .. (?P<pty>[^:]+?)(?::(?P<name>.+?))?=(?P<val>.*) .."
                    cell = cell_m.group("cell")
                    for m in re.finditer(property_regex, cell_m.group("body")):
                        d = m.groupdict()
                        if d["pty"] == "hdlname":
                            self.enable_cells[d["name"]]["enable"] = cell
                        elif d["pty"] == "scy_line":
                            line = int(d["val"], base=2)
                            if line:
                                self.add_cells[line]["cell"] = cell

        # modify config for full sby runs
        common_il = os.path.join('common', 'model', 'design_prep.il')
        self.sbycfg.prep_shared(common_il)

        for name, vals in self.enable_cells.items():
            task_cell = self.enable_cells[name].copy()
            if not vals.get("does_enable", False):
                task_cell["status"] = "enable"
                common_task.add_enable_cell(name, task_cell)
            elif not vals.get("does_disable", False):
                task_cell["status"] = "disable"
                common_task.add_enable_cell(name, task_cell)

        common_task.update_children_enable_cells(recurse=False)

        childrenp = await asyncio.gather(
            *[self.run_task(child) for child in common_task.children]
        )
        for childp in childrenp:
            p.extend(childp)

        return p

    async def run_task(self, task: TaskTree, recurse=True):
        p = []
        task_trace = None
        workdir = self.scycfg.args.workdir
        setupmode = self.scycfg.args.setupmode

        if task.uses_sby:
            # generate sby
            taskcfg = gen_sby(task, self.sbycfg, self.scycfg,
                              self.add_cells, self.enable_cells)
            task_sby = os.path.join(f"{workdir}", 
                                    f"{task.dir}.sby")
            print(f"Generating {task_sby}")
            with open(task_sby, 'w') as sbyfile:
                taskcfg.dump(sbyfile)
            task_trace = f"{task.tracestr}.{self.scycfg.options.trace_ext}"
            if not setupmode:
                # run sby
                sby_args = ["sby", "-f", f"{task.dir}.sby"]
                p.append(await runner(self.client, sby_args, workdir))
        elif task.stmt == "trace":
            if self.scycfg.options.replay_vcd:
                raise NotImplementedError(f"replay_vcd option with trace statement on line {task.line}")
            if not task.is_leaf:
                raise NotImplementedError(f"trace statement has children on line {task.line}")
            assert not task.is_root, f"trace statement is root on line {task.line}"

            if not setupmode:
                # prepare yosys
                traces = gen_traces(task)

                # run yosys-witness to concatenate all traces
                yw_args = ["yosys-witness", "yw2yw"]
                for trace in traces:
                    yw_args.extend(trace.split())

                # now use yosys to replay trace and generate vcd
                yw_args.append(f"{task.name}.yw")
                p.append(await runner(self.client, yw_args, workdir))
                common_il = self.sbycfg.files[0].split()[-1]
                yosys_args = [
                    "yosys", "-p", 
                    f"read_rtlil {common_il}; sim -hdlname -r {task.name}.yw -vcd {task.name}.vcd"
                ]
                p.append(await runner(self.client, yosys_args, workdir))
        elif task.stmt == "append":
            if self.scycfg.options.replay_vcd:
                raise NotImplementedError(f"replay_vcd option with append statement on line {task.line}")
            task.traces[-1] += f" -append {int(task.name):d}"
            self.task_steps[f"{task.linestr}_{task.name}"] = int(task.name)
        elif task.stmt == "add":
            add_cell = self.add_cells[task.line]
            task.add_enable_cell(add_cell["cell"], add_cell)
            task.reduce_depth()
        elif task.stmt in ["enable", "disable"]:
            task_cell = self.enable_cells[task.name].copy()
            task_cell["status"] = task.stmt
            task_cell["line"] = task.line
            task.add_or_update_enable_cell(task.name, task_cell)
        else:
            raise NotImplementedError(f"unknown stament {task.stmt!r} on line {task.line}")

        # add traces to children
        task.update_children_traces(task_trace)
        task.update_children_enable_cells(recurse=False)

        if recurse:
            childrenp = await asyncio.gather(
                *[self.run_task(child, recurse) for child in task.children]
            )
            for childp in childrenp:
                p.extend(childp)

        return p

