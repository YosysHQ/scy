#!/usr/bin/env python3

import os, sys, re
import argparse
import asyncio
import json
import shutil
##yosys-sys-path##
from scy_cmdline import parser_func
from scy_config_parser import SCYConfig
from scy_sby_bridge import SBYBridge
from scy_task_runner import TaskRunner, runner
from scy_task_tree import TaskTree
from yosys_mau import source_str
import yosys_mau.task_loop.job_server as job

parser = parser_func()

args = parser.parse_args()
scyfile = args.scyfile
workdir = args.workdir
if workdir is None:
    workdir = args.workdir = scyfile.split('.')[0]

# parse scy file
scy_source = source_str.read_file(scyfile)

scycfg = SCYConfig(scy_source)
scycfg.args = args

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

# prepare sby files
sbycfg = SBYBridge.from_scycfg(scycfg)

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
    sbycfg.script.extend([f"add -{cell['type']} {cell['lhs']} # line {line}",
                          f"setattr -set scy_line {line}  w:{cell['lhs']} %co c:$auto$add* %i"])
for hdlname in enable_cells.keys():
    select = f"w:*:*_EN c:{hdlname} %ci:+[EN] %i"
    sbycfg.script.append(f"setattr -set scy_line 0 -set hdlname:{hdlname} 1 {select}")
if add_cells or enable_cells:
    add_log = "add_cells.log"
    sbycfg.script.append(f"tee -o {add_log} printattrs a:scy_line")
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

retcode = 0
sby_args = ["sby", "common.sby"]
print(f'Running "{" ".join(sby_args)}"')
p = asyncio.run(runner(client, sby_args, workdir))
retcode = p.returncode

if retcode:
    sby_logfile = os.path.join(workdir, 'common', 'logfile.txt')
    print(f"Something went wrong!  Check {sby_logfile} for more info")
    print(read_pipe(p.stderr))
    sys.exit(retcode)
elif args.dump_common:
    sys.exit(0)

if scycfg.options.replay_vcd and not scycfg.options.design_scope:
    # load top level design name back from generated model
    design_json = os.path.join(workdir, "common", "model", "design.json")
    with open(design_json, 'r') as f:
        design = json.load(f)

    assert len(design["modules"]) == 1, "expected one top level module"
    scycfg.options.design_scope = design["modules"][0]["name"]

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

# execute task tree
task_runner = TaskRunner(sbycfg, scycfg, client, add_cells, enable_cells)

p_all = asyncio.run(task_runner.run_task(scycfg.sequence, recurse=True))

make_log = ""
for p in p_all:
    retcode = p.returncode
    if retcode:
        print(read_pipe(p.stderr))
        sys.exit(retcode)
    make_log += read_pipe(p.stdout)

if args.setupmode:
    sys.exit(0)

# parse sby runs
log_regex = r"^.*\[(?P<task>.*)\].*(?:reached).*step (?P<step>\d+)$"
log_matches = re.finditer(log_regex, make_log, flags=re.MULTILINE)
task_steps = task_runner.task_steps
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
