import os
import json
import re
from pathlib import Path
from typing import cast

from scy.scy_task_tree import TaskTree
from scy.scy_config_parser import SCYConfig
from scy.scy_sby_bridge import (
    gen_sby,
    parse_common_sby,
    SBYBridge,
)
from scy.scy_exceptions import (
    SCYSubProcessException,
    SCYTreeError,
    SCYUnknownCellError,
    SCYUnknownStatementError,
    SCYValueError
)

import yosys_mau.task_loop as tl
from yosys_mau.task_loop import (
    LogContext,
    log,
    log_exception,
)

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

def dump_trace(task: TaskTree, workdir: Path):
    # prepare yosys
    traces = gen_traces(task)

    # run yosys-witness to concatenate all traces
    yw_args = ["yosys-witness", "yw2yw"]
    for trace in traces:
        yw_args.extend(trace.split())

    # now use yosys to replay trace and generate vcd
    yw_args.append(f"{task.name}.yw")
    yw_proc = tl.Process(yw_args, cwd=workdir)
    yw_proc.events(tl.process.ExitEvent).handle(on_proc_exit)
    yw_proc.events(tl.process.StderrEvent).handle(on_proc_err)
    common_il = SCYRunnerContext.sbycfg.files[0].split()[-1]
    yosys_args = [
        "yosys", "-p",
        f"read_rtlil {common_il}; sim -hdlname -r {task.name}.yw -vcd {task.name}.vcd"
    ]
    yosys_proc = tl.Process(yosys_args, cwd=workdir)
    yosys_proc.depends_on(yw_proc)
    yosys_proc.events(tl.process.ExitEvent).handle(on_proc_exit)
    yosys_proc.events(tl.process.StderrEvent).handle(on_proc_err)
    return yosys_proc

def on_proc_err(event: tl.process.StderrEvent):
    tl.log_warning(event.output)

async def on_proc_exit(event: tl.process.ExitEvent):
    if event.returncode != 0:
        # find what failed
        event_task = cast(tl.Process, event.source)
        exe_name = event_task.command[0]

        # run bridge error handler
        if "sby" in exe_name:
            err = SCYRunnerContext.sbycfg.handle_error(
                event_task, SCYRunnerContext.scycfg.args.check_error, SCYTaskContext.task
            )
        else:
            # generic error handler
            event_cmd = " ".join(event_task.command)

            # check reported error
            bestguess = None
            if SCYRunnerContext.scycfg.args.check_error:
                if "yosys-witness" in exe_name:
                    bestguess = "may be missing yw_join feature"

            # log and raise error
            err = SCYSubProcessException(event_cmd, None, bestguess)
        tl.log_exception(err)

@tl.task_context
class SCYRunnerContext:
    sbycfg: SBYBridge
    scycfg: SCYConfig
    add_cells: "dict[int, dict[str]]"
    enable_cells: "dict[str, dict[str, str | bool]]"
    task_steps: "dict[str, int]"

@tl.task_context
class SCYTaskContext:
    task: TaskTree
    recurse: bool

async def handle_cover_output(lines):
    steps_regex = r"^.*\[(?P<task>.*)\].*(?:reached).*step (?P<step>\d+)$"
    async for line_event in lines:
        step_match = re.match(steps_regex, line_event.output)
        if step_match:
            task_steps = SCYRunnerContext.task_steps
            task_steps[step_match['task']] = int(step_match['step'])

def run_children(children: "list[TaskTree]", blocker: "tl.Task"):
    for child in children:
        child_task = tl.Task(on_run=run_task)
        child_task[SCYTaskContext].task = child
        if blocker:
            child_task.depends_on(blocker)

def load_design():
    workdir = Path(SCYRunnerContext.scycfg.args.workdir)
    design_json = workdir / "common" / "model" / "design.json"
    with open(design_json, 'r') as f:
        design = json.load(f)

    assert len(design["modules"]) == 1, ("expected one top level module, "
                                        "try setting the 'design_scope' option")
    SCYRunnerContext.scycfg.options.design_scope = design["modules"][0]["name"]

def run_tree():
    # loading context
    LogContext.scope = "common"
    sbycfg = SCYRunnerContext.sbycfg
    scycfg = SCYRunnerContext.scycfg
    common_task = scycfg.root
    workdir = Path(SCYRunnerContext.scycfg.args.workdir)
    try:
        (add_log, add_cells, enable_cells) = parse_common_sby(common_task, sbycfg, scycfg)
    except NotImplementedError as e:
        log_exception(e)

    # use sby to prepare input
    log(f"preparing input files")
    task_sby = workdir / "common.sby"

    with open(task_sby, 'w') as sbyfile:
        sbycfg.dump_common(sbyfile)

    if scycfg.args.dump_common:
        return

    sby_args = ["sby", "common.sby"]
    root_task = tl.Process(sby_args, cwd=workdir)
    root_task.events(tl.process.ExitEvent).handle(on_proc_exit)
    root_task.events(tl.process.StderrEvent).handle(on_proc_err)

    if scycfg.options.replay_vcd and not scycfg.options.design_scope:
        # load top level design name back from generated model
        design_task = tl.Task(on_run=load_design)
        design_task.depends_on(root_task)
        root_task = design_task

    def parse_add_log():
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

        for name, vals in enable_cells.items():
            task_cell = enable_cells[name].copy()
            if not vals.get("does_enable", False):
                task_cell["status"] = "enable"
                common_task.add_enable_cell(name, task_cell)
            elif not vals.get("does_disable", False):
                task_cell["status"] = "disable"
                common_task.add_enable_cell(name, task_cell)

        common_task.update_children_enable_cells(recurse=False)

    if add_log:
        parse_adds_task = tl.Task(on_run=parse_add_log)
        parse_adds_task.depends_on(root_task)
        root_task = parse_adds_task

    # modify config for full sby runs
    common_il = os.path.join('common', 'model', 'design_prep.il')
    sbycfg.prep_shared(common_il)

    SCYRunnerContext.add_cells = add_cells
    SCYRunnerContext.enable_cells = enable_cells
    SCYTaskContext.recurse = True
    run_children(common_task.children, root_task)

def run_task():
    # loading context
    task = SCYTaskContext.task
    workdir = Path(SCYRunnerContext.scycfg.args.workdir)
    setupmode = SCYRunnerContext.scycfg.args.setupmode
    LogContext.scope = task.full_line.strip(" \t:")

    # default values
    task_trace = None
    root_task = None

    if task.uses_sby:
        # generate sby
        taskcfg = gen_sby(task, SCYRunnerContext.sbycfg, SCYRunnerContext.scycfg,
                            SCYRunnerContext.add_cells, SCYRunnerContext.enable_cells)
        task_sby = workdir / f"{task.dir}.sby"
        log(f"generating {task_sby}")
        with open(task_sby, 'w') as sbyfile:
            taskcfg.dump(sbyfile)
        task_trace = f"{task.tracestr}.{SCYRunnerContext.scycfg.options.trace_ext}"
        if not setupmode:
            # run sby
            sby_args = ["sby", "-f", f"{task.dir}.sby"]
            root_task = tl.Process(sby_args, cwd=workdir)
            root_task.events(tl.process.ExitEvent).handle(on_proc_exit)
            root_task.events(tl.process.OutputEvent).process(handle_cover_output)
    elif task.stmt == "trace":
        if SCYRunnerContext.scycfg.options.replay_vcd:
            log_exception(SCYTreeError(task.stmt, "replay_vcd option incompatible with trace statement"))
        if not task.is_leaf:
            log_exception(SCYTreeError(task.children[0].stmt, "trace statement does not support children"))
        if task.is_root or task.parent.is_common:
            log_exception(SCYTreeError(task.full_line, "trace statement cannot be root task"))
        if not SCYRunnerContext.sbycfg.files:
            log_exception(SCYTreeError(task.full_line, "trace requires common sby generation"))

        if not setupmode:
            dump_trace(task, workdir)
    elif task.stmt == "append":
        if SCYRunnerContext.scycfg.options.replay_vcd:
            log_exception(SCYTreeError(task.stmt, "replay_vcd option incompatible with append statement"))
        if task.is_root or task.parent.is_common:
            log_exception(SCYTreeError(task.full_line, "append statement cannot be root task"))
        try:
            task.traces[-1] += f" -append {int(task.name):d}"
        except IndexError:
            log_exception(SCYTreeError(task.full_line, f"append expected parent task to produce a trace"))
        except ValueError:
            log_exception(SCYValueError(task.name, "must be integer literal"))
        SCYRunnerContext.task_steps[f"{task.linestr}_{task.name}"] = int(task.name)
    elif task.stmt == "add":
        try:
            add_cell = SCYRunnerContext.add_cells[task.line]
        except KeyError:
            log_exception(SCYUnknownCellError(task.full_line, f"attempted to add unknown cell"))
        task.add_enable_cell(add_cell["cell"], add_cell)
        task.reduce_depth()
    elif task.stmt in ["enable", "disable"]:
        try:
            task_cell = SCYRunnerContext.enable_cells[task.name].copy()
        except KeyError:
            log_exception(SCYUnknownCellError(task.full_line, f"attempted to {task.stmt} unknown cell"))
        task_cell["status"] = task.stmt
        task_cell["line"] = task.line
        task.add_or_update_enable_cell(task.name, task_cell)
    else:
        # this shouldn't happen since an unrecognised statement should have been caught by the tree parse
        log_exception(SCYUnknownStatementError(task.full_line, "unrecognised statement"))

    # add traces to children
    task.update_children_traces(task_trace)
    task.update_children_enable_cells(recurse=False)

    if SCYTaskContext.recurse:
        run_children(task.children, root_task)
