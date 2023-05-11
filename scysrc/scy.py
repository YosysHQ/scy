import os, sys, re
import argparse
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
    os.makedirs(workdir, exist_ok=args.force)
except FileExistsError:
    print(f"ERROR: Directory '{workdir}' already exists, use -f to overwrite the existing directory.")
    sys.exit(1)

# generate sby files
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
        # add extra options
        body += "\n".join(["mode cover", 
                           "expect pass", 
                           ""])
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
                if name == "script":
                    # load parent trace
                    body += '\n'.join(["setundef -zero",
                                      "sim -w -r trace0.yw",
                                      ""])
                elif name == "files":
                    parent_yw = os.path.join(parent_dir,
                                             "engine_0",
                                             "trace0.yw")
                    body += f"\n{parent_yw}\n"
            if name == "script":
                # enable only relevant cover
                body += f"\ndelete t:$cover a:hdlname=*{task.name} %d\n"
            print(f"[{name}]", file=sbyfile)
            print(body, file=sbyfile)

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
print(f"Running {' '.join(make_args)}")
p = subprocess.run(make_args, capture_output=True)
retcode = p.returncode

# parse sby runs

# output stats

sys.exit(retcode)
