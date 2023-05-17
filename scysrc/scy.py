import os, sys, re
import argparse
import json
import shutil
import subprocess
from scy_task_tree import TaskTree

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

with open(scyfile, 'r') as f:
    scydata = f.read()

stmt_regex = r"(?:^|\n)\[(?P<name>.*)\]\n(?P<body>(?:\n?.*)*?(?=\n\[|$))"
sections = re.finditer(stmt_regex, scydata)
scycfg = { m['name']:m['body'] for m in sections }

start_index = scydata.split('\n').index("[sequence]") + 2
task_tree = TaskTree.from_string(scycfg["sequence"], L0 = start_index)

if args.dump_tree:
    print(task_tree)
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

# default assignments
sbycfg = {"engines": "smtbmc boolector", 
          "files": ""}
for (name, body) in scycfg.items():
    if name in ["sequence"]: 
        # skip any scy specific sections
        continue
    elif name == "options": 
        # remove any scy specific options
        pass
    elif name == "design":
        # rename design to script
        name = "script"
    elif name == "files":
        # correct relative paths for extra level of depth
        newbody = ""
        for line in body.split('\n'):
            if line:
                if not os.path.isabs(line):
                    line = os.path.join("..", line)
                newbody += line + '\n'
        body = newbody
    sbycfg[name] = body

# use sby to prepare input
print(f"Preparing input files")
task_sby = os.path.join(f"{workdir}", 
                        f"common.sby")
with open(task_sby, 'w') as sbyfile:
    for (name, body) in sbycfg.items():
        if name in "engines":
            continue
        elif name == "options":
            body = sby_body_append(body, "mode prep")
        print(f"[{name}]", file=sbyfile)
        print(body, file=sbyfile)
retcode = 0
sby_args = ["sby", "common.sby"]
print(f'Running "{" ".join(sby_args)}"')
p = subprocess.run(sby_args, cwd=workdir, capture_output=True)
retcode = p.returncode

if args.dump_common or retcode:
    sys.exit(retcode)

# load top level design name back from generated model
design_json = os.path.join(workdir, "common", "model", "design.json")
with open(design_json, 'r') as f:
    design = json.load(f)

assert len(design["modules"]) == 1, "expected one top level module"
design_scope = design["modules"][0]["name"]

# modify config for full sby runs
sbycfg["options"] = sby_body_append(
        sbycfg["options"], ["mode cover", 
                            "expect pass",
                            "skip_prep on"])
sbycfg["script"] = sby_body_append("", ["read_rtlil common_design.il"])
sbycfg["files"] = sby_body_append("", [f"common_design.il {os.path.join('common', 'model', 'design_prep.il')}"])
for key in list(sbycfg.keys()):
    if "file " in key:
        sbycfg.pop(key)

make_all = []
make_deps = {}
for task in task_tree.traverse():
    # each task has its own sby file
    task_dir = f"{task.get_linestr()}_{task.name}"
    make_all.append(task_dir)
    task_sby = os.path.join(f"{workdir}", 
                            f"{task_dir}.sby")
    print(f"Generating {task_sby}")
    with open(task_sby, 'w') as sbyfile:
        for (name, body) in sbycfg.items():
            if not task.is_root():
                # child nodes depend on parent
                parent = task.parent
                parent_dir = f"{parent.get_linestr()}_{parent.name}"
                make_deps[task_dir] = parent_dir
                if name == "files":
                    parent_yw = os.path.join(parent_dir,
                                             "engine_0",
                                             "trace0.vcd")
                    traces = [os.path.join(parent_dir,
                                           "src", 
                                           trace) for trace in task.traces[:-1]]
                    body = sby_body_append(body, 
                                           traces + [f"{task.parent.get_tracestr()} {parent_yw}"])
            if name == "script":
                # replay prior traces and enable only relevant cover
                traces_script = []
                for trace in task.traces:
                    traces_script += [f"sim -w -r {trace} -scope {design_scope}"]
                body = sby_body_append(body, 
                                       traces_script + [f"delete t:$cover a:hdlname=*{task.name} %d"])
            print(f"[{name}]", file=sbyfile)
            print(body, file=sbyfile)
    # add this trace to child
    for child in task.children:
        child.traces += task.traces + [task.get_tracestr()]

# generate makefile
makefile = os.path.join(workdir, "Makefile")
print(f"Generating {makefile}")
with open(makefile, "w") as mk:
    print(f"all: {' '.join(make_all)}", file=mk)
    print("""%:%.sby
	sby -f $<
""", file=mk)
    for (task, dep) in make_deps.items():
        print(f"{task}: {dep}", file=mk)

if args.setupmode:
    sys.exit(0)

# run makefile
retcode = 0
make_args = ["make"]
if args.jobcount:
    make_args.append(f"-j{args.jobcount}")
make_args += ["-C", workdir]
print(f'Running "{" ".join(make_args)}"')
p = subprocess.run(make_args, capture_output=True)
retcode = p.returncode
make_log = str(p.stdout, encoding="utf-8")

with open(makefile + ".log", 'w') as f:
    print(make_log, file=f)

if retcode:
    print("Something went wrong!")
    p.check_returncode()

# parse sby runs
log_regex = r"^.*\[(?P<task>.*)\].*(?:reached).*step (?P<step>\d+)$"
log_matches = re.finditer(log_regex, make_log, flags=re.MULTILINE)
task_steps = {m['task']:int(m['step']) for m in log_matches}

# output stats
print("Chunks:")
for task in task_tree.traverse():
    task.steps = task_steps[f"{task.get_linestr()}_{task.name}"]
    chunk_str = " "*task.depth + f"L{task.line}"
    cycles_str = f"{task.start_cycle():2} .. {task.stop_cycle():2}"
    print(f"  {chunk_str:6}  {cycles_str}  =>  {task.steps:2}  {task.name}")

sys.exit(retcode)
