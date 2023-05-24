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
opt_replay_vcd = False
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
        newbody = ""
        for line in body.split('\n'):
            if line:
                key, val = line.split(maxsplit=1)
                if key == "replay_vcd":
                    opt_replay_vcd = val == "on"
                else:
                    newbody += line + '\n'
        body = newbody
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

# preparse tree to extract cell generation
add_cells: "dict[int, dict[str]]" = {}
enable_cells: "dict[str, dict[str, str | bool]]" = {}
for task in task_tree.traverse():
    if task.stmt == "add":
        if task.name not in ["assert", "assume", "live", "fair", "cover"]:
            raise NotImplementedError(f"cell type {task.name!r} on line {task.line}")
        add_cells[task.line] = {"type": task.name}
        add_cells[task.line].update(task.get_asgmt())
    if task.stmt in ["enable", "disable"]:
        enable_cells.setdefault(task.name, {"disable": "1'b0"})
        enable_cells[task.name][f"does_{task.stmt}"] = True

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
        if name == "script":
            for (line, cell) in add_cells.items():
                body = sby_body_append(body, [f"add -{cell['type']} {cell['lhs']} # line {line}",
                                              f"setattr -set scy_line {line}  w:{cell['lhs']} %co c:$auto$add* %i"])
            for hdlname in enable_cells.keys():
                select = f"w:*:*_EN c:{hdlname} %ci:+[EN] %i"
                body = sby_body_append(body, f"setattr -set scy_line 0 -set hdlname \"{hdlname}\" {select}")
            if add_cells:
                add_log = "add_cells.log"
                body = sby_body_append(body, f"tee -o {add_log} printattrs a:scy_line")
                add_log = os.path.join(workdir, "common", "src", add_log)
        print(f"[{name}]", file=sbyfile)
        print(body, file=sbyfile)
retcode = 0
sby_args = ["sby", "common.sby"]
print(f'Running "{" ".join(sby_args)}"')
p = subprocess.run(sby_args, cwd=workdir, capture_output=True)
retcode = p.returncode

if retcode:
    sby_logfile = os.path.join(workdir, 'common', 'logfile.txt')
    print(f"Something went wrong!  Check {sby_logfile} for more info")
    print(str(p.stderr, encoding="utf-8"))
    sys.exit(retcode)
elif args.dump_common:
    sys.exit(0)

if opt_replay_vcd:
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
        cell_regex = r"(?P<cell>\S*)(?:\n  (.. scy_line=(?P<scy_line>\d+) ..|.. hdlname=\"(?P<hdlname>.*)\" ..|(?:.*)))*"
        for m in re.finditer(cell_regex, cell_dump):
            d = m.groupdict()
            if not d["cell"]:
                continue
            if d["hdlname"]:
                name = d["hdlname"].split()[-1]
                enable_cells[hdlname]["enable"] = d["cell"]
            else:
                line = int(d["scy_line"], base=2)
                add_cells[line]["cell"] = d["cell"]

# modify config for full sby runs
sbycfg["options"] = sby_body_append(
        sbycfg["options"], ["mode cover", 
                            "expect pass",
                            "skip_prep on"])
sbycfg["script"] = sby_body_append("", ["read_rtlil common_design.il"])
common_il = os.path.join('common', 'model', 'design_prep.il')
sbycfg["files"] = sby_body_append("", [f"common_design.il {common_il}"])
for key in list(sbycfg.keys()):
    if "file " in key:
        sbycfg.pop(key)

make_all = []
make_deps = {}
task_steps = {}
for task in task_tree.traverse():
    task_trace = None
    if task.is_root():
        for name, vals in enable_cells.items():
            if not vals.get("does_enable", False):
                task.enable_cells[name] = enable_cells[name].copy()
                task.enable_cells[name]["status"] = "enable"
            elif not vals.get("does_disable", False):
                task.enable_cells[name] = enable_cells[name].copy()
                task.enable_cells[name]["status"] = "disable"

    # each task has its own sby file
    if task.is_runnable():
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
                    parent_dir = task.parent.get_dir()
                    make_deps[task_dir] = parent_dir
                    if name == "files":
                        parent_yw = os.path.join(parent_dir,
                                                "engine_0",
                                                f"trace0.{trace_ext}")
                        traces = [os.path.join(parent_dir,
                                            "src", 
                                            trace.split()[0]) for trace in task.traces[:-1]]
                        body = sby_body_append(body, 
                                            traces + [f"{parent.get_tracestr()}.{trace_ext} {parent_yw}"])
                if name == "script":
                    # configure additional cells
                    connect_commands = []
                    for cell in add_cells.values():
                        en_sig = '1' if cell["cell"] in task.enable_cells else '0'
                        connect_commands.append(f"connect -port {cell['cell']} \EN 1'b{en_sig}")
                    for hdlname in enable_cells.keys():
                        task_cell = task.enable_cells.get(hdlname, None)
                        if task_cell:
                            en_sig = task_cell[task_cell["status"]]
                            connect_commands.append(f"connect -port {hdlname} \EN {en_sig}")
                            if task_cell["status"] == "enable":
                                connect_commands.append(f"chformal -skip 1 c:{hdlname}")
                    body = sby_body_append(body, connect_commands)
                    # replay prior traces and enable only relevant cover
                    traces_script = []
                    for trace in task.traces:
                        trace_scope = f" -scope {design_scope}" if opt_replay_vcd else ""
                        traces_script.append(f"sim -w -r {trace}{trace_scope}")
                    if task.stmt == "cover":
                        traces_script.append(f"delete t:$cover a:hdlname=*{task.name} %d")
                        body = sby_body_append(body, traces_script)
                    else:
                        raise NotImplementedError(task.stmt)
                print(f"[{name}]", file=sbyfile)
                print(body, file=sbyfile)
        task_trace = f"{task.get_tracestr()}.{trace_ext}"
    elif task.stmt == "append":
        if opt_replay_vcd:
            raise NotImplementedError(f"replay_vcd option with append statement on line {task.line}")
        task.traces[-1] += f" -append {int(task.name):d}"
        task_steps[f"{task.get_linestr()}_{task.name}"] = int(task.name)
    elif task.stmt == "trace":
        if opt_replay_vcd:
            raise NotImplementedError(f"replay_vcd option with trace statement on line {task.line}")
        if not task.is_leaf():
            raise NotImplementedError(f"trace statement has children on line {task.line}")
        if task.is_root():
            raise NotImplementedError(f"trace statement is root on line {task.line}")

        trace_list = [f"{task.name}.{ext}" for ext in ["yw", "vcd"]]
        make_all += trace_list
        
        parent_dir = task.parent.get_dir()
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
                trace_path = os.path.join(parent_dir,
                                          "engine_0",
                                          "trace0.yw")
            else:
                # using sim -w appears to combine the final step of one trace with the first step of the next
                # we emulate this by telling yosys-witness to skip one extra cycle than we told sim
                append -= 1
                trace_path = os.path.join(parent_dir,
                                          "src", 
                                          trace)
            traces.append(f"{trace_path} -p {append}")

        # we now need to flip the order back to the expected order
        task.traces.reverse()
        traces.reverse()
        make_deps[trace_list[1]] = trace_list[0]
        make_deps[trace_list[0]] = f'{parent_dir}\n\tyosys-witness yw2yw {" ".join(traces)} $@'
    elif task.stmt == "add":
        add_cell = add_cells[task.line]
        task.enable_cells[add_cell["cell"]] = add_cell
        task.reduce_depth()
    elif task.stmt in ["enable", "disable"]:
        if task.name not in task.enable_cells:
            task.enable_cells[task.name] = enable_cells[task.name].copy()
        task.enable_cells[task.name]["status"] = task.stmt
        task.enable_cells[task.name]["line"] = task.line
    else:
        raise NotImplementedError(f"unknown stament {task.stmt!r} on line {task.line}")
    
    # add traces to children
    for child in task.children:
        child.traces.extend(task.traces)
        if task_trace:
            child.traces.append(task_trace)
        for k, v in task.enable_cells.items():
            try:
                child.enable_cells[k].update(v)
            except KeyError:
                child.enable_cells[k] = v.copy()

# generate makefile
makefile = os.path.join(workdir, "Makefile")
print(f"Generating {makefile}")
with open(makefile, "w") as mk:
    print(f"all: {' '.join(make_all)}", file=mk)
    print("%:%.sby\n\tsby -f $<", file=mk)
    print(f"%.vcd: %.yw\n\tyosys -p 'read_rtlil {common_il}; sim -hdlname -r $< -vcd $@'", file=mk)
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
    print(f"Something went wrong!  Check {makefile}.log for more info")
    print(str(p.stderr, encoding="utf-8"))
    sys.exit(retcode)

# parse sby runs
log_regex = r"^.*\[(?P<task>.*)\].*(?:reached).*step (?P<step>\d+)$"
log_matches = re.finditer(log_regex, make_log, flags=re.MULTILINE)
task_steps.update({m['task']:int(m['step']) for m in log_matches})

# output stats
trace_tasks = []
print("Chunks:")
for task in task_tree.traverse():
    if task.stmt == "trace":
        trace_tasks.append(task)
    if task.stmt not in ["append", "cover"]:
        continue
    task.steps = task_steps[f"{task.get_linestr()}_{task.name}"]
    chunk_str = " "*task.depth + f"L{task.line}"
    cycles_str = f"{task.start_cycle():2} .. {task.stop_cycle():2}"
    task_str = task.name if task.is_runnable() else f"{task.stmt} {task.name}"
    print(f"  {chunk_str:6}  {cycles_str}  =>  {task.steps:2}  {task_str}")

print("\nTraces:")
for task in trace_tasks:
    cycles_str = f"{task.stop_cycle() + 1:>2} cycles"
    chunks = task.parent.get_all_linestr()
    chunks.sort()
    chunks_str = " ".join(chunks)
    print(f"  {task.name:12} {cycles_str} [{chunks_str}]")

sys.exit(0)
