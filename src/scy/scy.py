#!/usr/bin/env python3

import os, sys, re
import asyncio
import shutil
from scy.scy_cmdline import parser_func
from scy.scy_config_parser import SCYConfig
from scy.scy_sby_bridge import SBYBridge
from scy.scy_task_runner import TaskRunner
from yosys_mau import source_str
import yosys_mau.task_loop.job_server as job

from scy.scy_task_tree import TaskTree

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
    for seq in scycfg.sequence:
        if isinstance(seq, TaskTree):
            print(seq)
    sys.exit(0)

client = job.Client(args.jobcount)

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

# add common sby generation task
scycfg.root = TaskTree("", "common", 0).add_children(scycfg.sequence)

# execute task tree
task_runner = TaskRunner(sbycfg, scycfg, client)

p_all = asyncio.run(task_runner.run_tree())

def read_pipe(pipe: asyncio.StreamReader):
    return asyncio.run(read_pipe_async(pipe))

async def read_pipe_async(pipe: asyncio.StreamReader):
    result = await pipe.read()
    return bytes.decode(result)

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
for task in scycfg.root.traverse():
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

def main():
    # this seems lazy, because it is
    pass
