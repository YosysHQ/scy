#!/usr/bin/env python3

import os, sys, re
import argparse
import asyncio
import json
import shutil
##yosys-sys-path##
from scy_task_tree import TaskTree
from scy_config_parser import SCYConfig
from scy_sby_bridge import SBYBridge
from yosys_mau import source_str
import yosys_mau.task_loop.job_server as job

parser = argparse.ArgumentParser(prog="scy")

# input arguments
# mostly just a quick hack while waiting for common frontend
parser.add_argument("-d", metavar="<dirname>", dest="workdir",
        help="set workdir name. default: <jobname>")
parser.add_argument("-f", action="store_true", dest="force",
        help="remove workdir if it already exists")

parser.add_argument("-j", metavar="<N>", type=int, dest="jobcount",
        help="maximum number of processes to run in parallel")

parser.add_argument("--dumptree", action="store_true", dest="dump_tree",
        help="print the task tree and exit")
parser.add_argument("--dumpcommon", action="store_true", dest="dump_common",
        help="prepare common input and exit")
parser.add_argument("--setup", action="store_true", dest="setupmode",
        help="set up the working directory and exit")

parser.add_argument('scyfile', metavar="<jobname>.scy",
        help=".scy file")

args = parser.parse_args()
scyfile = args.scyfile
workdir = args.workdir
if workdir is None:
    workdir = scyfile.split('.')[0]

# parse scy file
scy_source = source_str.read_file(scyfile)

scycfg = SCYConfig(scy_source)

if args.dump_tree:
    print(scycfg.sequence)
    sys.exit(0)

# generate workdir
try:
    os.makedirs(workdir)
except FileExistsError:
    if args.force:
        shutil.rmtree(workdir, ignore_errors=True)
        os.makedirs(workdir)
    else:
        print(f"ERROR: Directory '{workdir}' already exists, use -f to overwrite the existing directory.")
        sys.exit(1)

# generate sby files
def sby_body_append(body: str, append: "str | list[str]"):
    if len(body) > 1:
        if body[-1] != '\n':
            body += '\n'
        elif body[-2] == '\n':
            body = body[:-1]
    if isinstance(append, str):
        append = [append]
    elif append and append[-1]:
        append.append("")
    body += '\n'.join(append)
    return body

# dump sby config options out
sbycfg = SBYBridge()
sbycfg.add_section("options", scycfg.options.sby_options)
sbycfg.add_section("script", scycfg.design)
sbycfg.add_section("engines", scycfg.engines)

for sect in scycfg.fallback:
    name = sect.name
    if sect.arguments: name += f" {sect.arguments}"
    sbycfg.add_section(name, sect.contents)

sbycfg.fix_relative_paths("..")

# preparse tree to extract cell generation
add_cells: "dict[int, dict[str]]" = {}
enable_cells: "dict[str, dict[str, str | bool]]" = {}
def add_enable_cell(hdlname: str, stmt: str):
    enable_cells.setdefault(hdlname, {"disable": "1'b0"})
    enable_cells[hdlname][f"does_{stmt}"] = True

for task in scycfg.sequence.traverse():
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
    body = sby_body_append(body, [f"add -{cell['type']} {cell['lhs']} # line {line}",
                                    f"setattr -set scy_line {line}  w:{cell['lhs']} %co c:$auto$add* %i"])
for hdlname in enable_cells.keys():
    select = f"w:*:*_EN c:{hdlname} %ci:+[EN] %i"
    body = sby_body_append(body, f"setattr -set scy_line 0 -set hdlname:{hdlname} 1 {select}")
if add_cells or enable_cells:
    add_log = "add_cells.log"
    body = sby_body_append(body, f"tee -o {add_log} printattrs a:scy_line")
    add_log = os.path.join(workdir, "common", "src", add_log)

# use sby to prepare input
print(f"Preparing input files")
task_sby = os.path.join(f"{workdir}", 
                        f"common.sby")

with open(task_sby, 'w') as sbyfile:
    sbycfg.dump_common(sbyfile)

client = job.Client(args.jobcount)

def read_pipe(pipe: asyncio.StreamReader):
    return asyncio.run(read_pipe_async(pipe))

async def read_pipe_async(pipe: asyncio.StreamReader):
    result = await pipe.read()
    return bytes.decode(result)

async def runner(client: job.Client, exe_args: "list[str]"):
    lease = client.request_lease()
    await lease

    coro = await asyncio.create_subprocess_exec(
        *exe_args, cwd=workdir, 
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    await coro.wait()

    del lease
    return coro

retcode = 0
sby_args = ["sby", "common.sby"]
print(f'Running "{" ".join(sby_args)}"')
p = asyncio.run(runner(client, sby_args))
retcode = p.returncode

if retcode:
    sby_logfile = os.path.join(workdir, 'common', 'logfile.txt')
    print(f"Something went wrong!  Check {sby_logfile} for more info")
    print(read_pipe(p.stderr))
    sys.exit(retcode)
elif args.dump_common:
    sys.exit(0)

if scycfg.options.replay_vcd:
    # load top level design name back from generated model
    design_json = os.path.join(workdir, "common", "model", "design.json")
    with open(design_json, 'r') as f:
        design = json.load(f)

    assert len(design["modules"]) == 1, "expected one top level module"
    design_scope = design["modules"][0]["name"]
    trace_ext = "vcd"
else:
    trace_ext = "yw"

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
                    enable_cells[d["name"]]["enable"] = cell
                elif d["pty"] == "scy_line":
                    line = int(d["val"], base=2)
                    if line:
                        add_cells[line]["cell"] = cell

# modify config for full sby runs
common_il = os.path.join('common', 'model', 'design_prep.il')
sbycfg.prep_shared(common_il)

task_steps = {}
for task in scycfg.sequence.traverse():
    task_trace = None
    if task.is_root:
        for name, vals in enable_cells.items():
            task_cell = enable_cells[name].copy()
            if not vals.get("does_enable", False):
                task_cell["status"] = "enable"
                task.add_enable_cell(name, task_cell)
            elif not vals.get("does_disable", False):
                task_cell["status"] = "disable"
                task.add_enable_cell(name, task_cell)

    # each task has its own sby file
    if task.is_runnable:
        task_sby = os.path.join(f"{workdir}", 
                                f"{task.dir}.sby")
        print(f"Generating {task_sby}")
        with open(task_sby, 'w') as sbyfile:
            for (name, body) in sbycfg.data.items():
                body = "\n".join(body)
                if not task.is_root:
                    # child nodes depend on parent
                    parent = task.parent
                    parent_dir = task.parent.get_dir()
                    if name == "files":
                        parent_yw = os.path.join(parent_dir,
                                                "engine_0",
                                                f"trace0.{trace_ext}")
                        traces = [os.path.join(parent_dir,
                                            "src", 
                                            trace.split()[0]) for trace in task.traces[:-1]]
                        body = sby_body_append(body, 
                                            traces + [f"{parent.tracestr}.{trace_ext} {parent_yw}"])
                if name == "script":
                    # configure additional cells
                    pre_sim_commands = []
                    post_sim_commands = []
                    for cell in add_cells.values():
                        en_sig = '1' if cell["cell"] in task.enable_cells else '0'
                        pre_sim_commands.append(f"connect -port {cell['cell']} \EN 1'b{en_sig}")
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
                            pre_sim_commands.append(f"connect -port {hdlname} \EN {task_cell[status]}")
                            if status == "enable":
                                post_sim_commands.append(f"chformal -skip 1 c:{hdlname}")
                    body = sby_body_append(body, pre_sim_commands)
                    # replay prior traces and enable only relevant cover
                    traces_script = []
                    for trace in task.traces:
                        trace_scope = f" -scope {design_scope}" if scycfg.options.replay_vcd else ""
                        traces_script.append(f"sim -w -r {trace}{trace_scope}")
                    if task.stmt == "cover":
                        traces_script.append(f"delete t:$cover c:{task.name} %d")
                        body = sby_body_append(body, traces_script)
                    else:
                        raise NotImplementedError(task.stmt)
                    body = sby_body_append(body, post_sim_commands)
                print(f"[{name}]", file=sbyfile)
                print(body, file=sbyfile)
        task_trace = f"{task.tracestr}.{trace_ext}"
    elif task.stmt == "append":
        if scycfg.options.replay_vcd:
            raise NotImplementedError(f"replay_vcd option with append statement on line {task.line}")
        task.traces[-1] += f" -append {int(task.name):d}"
        task_steps[f"{task.linestr}_{task.name}"] = int(task.name)
    elif task.stmt == "trace":
        if scycfg.options.replay_vcd:
            raise NotImplementedError(f"replay_vcd option with trace statement on line {task.line}")
        if not task.is_leaf:
            raise NotImplementedError(f"trace statement has children on line {task.line}")
        if task.is_root:
            raise NotImplementedError(f"trace statement is root on line {task.line}")
    elif task.stmt == "add":
        add_cell = add_cells[task.line]
        task.add_enable_cell(add_cell["cell"], add_cell)
        task.reduce_depth()
    elif task.stmt in ["enable", "disable"]:
        task_cell = enable_cells[task.name].copy()
        task_cell["status"] = task.stmt
        task_cell["line"] = task.line
        task.add_or_update_enable_cell(task.name, task_cell)
    else:
        raise NotImplementedError(f"unknown stament {task.stmt!r} on line {task.line}")
    
    # add traces to children
    task.update_children_traces(task_trace)
    task.update_children_enable_cells(recurse=False)

if args.setupmode:
    sys.exit(0)

# execute task tree
async def tree_runner(client: job.Client, task: TaskTree):
    p = []
    # run self
    if task.is_runnable:
        sby_args = ["sby", "-f", f"{task.dir}.sby"]
        p.append(await runner(client, sby_args))
    elif task.stmt == "trace":
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
        p.append(await runner(client, yw_args))
        yosys_args = [
            "yosys", "-p", 
            f"read_rtlil {common_il}; sim -hdlname -r {task.name}.yw -vcd {task.name}.vcd"
        ]
        p.append(await runner(client, yosys_args))

    # run children
    children = await asyncio.gather(
        *[tree_runner(client, child) for child in task.children]
    )
    for child in children:
        p.extend(child)

    return p

p_all = asyncio.run(tree_runner(client, scycfg.sequence))

make_log = ""
for p in p_all:
    retcode = p.returncode
    if retcode:
        print(read_pipe(p.stderr))
        sys.exit(retcode)
    make_log += read_pipe(p.stdout)

# parse sby runs
log_regex = r"^.*\[(?P<task>.*)\].*(?:reached).*step (?P<step>\d+)$"
log_matches = re.finditer(log_regex, make_log, flags=re.MULTILINE)
task_steps.update({m['task']:int(m['step']) for m in log_matches})

# output stats
trace_tasks = []
print("Chunks:")
for task in scycfg.sequence.traverse():
    if task.stmt == "trace":
        trace_tasks.append(task)
    if task.stmt not in ["append", "cover"]:
        continue
    try:
        task.steps = task_steps[f"{task.linestr}_{task.name}"]
    except KeyError:
        print(f"No trace for {task.name} on line {task.line}, exiting.")
        sys.exit(1)
    chunk_str = " "*task.depth + f"L{task.line}"
    cycles_str = f"{task.start_cycle:2} .. {task.stop_cycle:2}"
    task_str = task.name if task.is_runnable else f"{task.stmt} {task.name}"
    print(f"  {chunk_str:6}  {cycles_str}  =>  {task.steps:2}  {task_str}")

if trace_tasks:
    print("\nTraces:")
for task in trace_tasks:
    cycles_str = f"{task.stop_cycle + 1:>2} cycles"
    chunks = task.parent.get_all_linestr()
    chunks.sort()
    chunks_str = " ".join(chunks)
    print(f"  {task.name:12} {cycles_str} [{chunks_str}]")

sys.exit(0)
