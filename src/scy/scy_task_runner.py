import asyncio
import copy
import os
from scy.scy_task_tree import TaskTree
from scy.scy_config_parser import SCYConfig
from scy.scy_sby_bridge import SBYBridge

import yosys_mau.task_loop.job_server as job

async def runner(client: job.Client, exe_args: "list[str]", workdir: str):
    lease = client.request_lease()
    await lease

    coro = await asyncio.create_subprocess_exec(
        *exe_args, cwd=workdir, 
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    await coro.wait()

    del lease
    return coro

def gen_sby(task: TaskTree, sbycfg: SBYBridge, scycfg: SCYConfig,
            add_cells: "dict[int, dict[str]]", 
            enable_cells: "dict[str, dict[str, str | bool]]"):

    if not task.is_root:
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

class TaskRunner():
    def __init__(self, sbycfg: SBYBridge, scycfg: SCYConfig, client: job.Client,
                 add_cells: "dict[int, dict[str]]" = {}, 
                 enable_cells: "dict[str, dict[str, str | bool]]" = {}):
        self.sbycfg = sbycfg
        self.scycfg = scycfg
        self.client = client
        self.add_cells = add_cells
        self.enable_cells = enable_cells
        self.task_steps = {}

    async def run_task(self, task: TaskTree, recurse=True):
        p = []
        task_trace = None
        workdir = self.scycfg.args.workdir
        setupmode = self.scycfg.args.setupmode
        # initialise root task with enable cells
        if task.is_root:
            for name, vals in self.enable_cells.items():
                task_cell = self.enable_cells[name].copy()
                if not vals.get("does_enable", False):
                    task_cell["status"] = "enable"
                    task.add_enable_cell(name, task_cell)
                elif not vals.get("does_disable", False):
                    task_cell["status"] = "disable"
                    task.add_enable_cell(name, task_cell)

        if task.uses_sby:
            # generate sby
            taskcfg = gen_sby(task, copy.deepcopy(self.sbycfg), self.scycfg,
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
            if task.is_root:
                raise NotImplementedError(f"trace statement is root on line {task.line}")
            if not setupmode:
                # prepare yosys
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

