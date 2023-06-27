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
    SCYTreeException,
    SCYSubProcessException
)

import yosys_mau.task_loop as tl

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

def on_sby_exit(event: tl.process.ExitEvent):
    if event.returncode != 0:
        event_task = cast(tl.Process, event.source)
        event_sby = Path(event_task.command[-1])
        event_dir = Path(event_task.cwd)
        err = SCYSubProcessException(target=event_sby, logfile=event_dir / event_sby.stem / 'logfile.txt')
        tl.log_exception(err)

class SingleTreeTask(tl.Task):
    def __init__(self, task_runner: "TaskRunner", task: TaskTree, recurse: bool):
        super().__init__()
        self.runner = task_runner
        self.task = task
        self.recurse = recurse

    async def on_run(self):
        return self.runner.run_task(self.task, self.recurse)

class TaskRunner():
    def __init__(self, sbycfg: SBYBridge, scycfg: SCYConfig):
        self.sbycfg = sbycfg
        self.scycfg = scycfg
        self.add_cells: "dict[int, dict[str]]" = {}
        self.enable_cells: "dict[str, dict[str, str | bool]]" = {}
        self.task_steps: "dict[str, int]" = {}

    async def handle_cover_output(self, lines):
        steps_regex = r"^.*\[(?P<task>.*)\].*(?:reached).*step (?P<step>\d+)$"
        async for line_event in lines:
            step_match = re.match(steps_regex, line_event.output)
            if step_match:
                self.task_steps[step_match['task']] = int(step_match['step'])

    def _run_tree_loop(self):
        tl.run_task_loop(self.run_tree)

    def _run_task_loop(self, task: TaskTree, recurse=True):
        tl.run_task_loop(lambda:self.run_task(task, recurse))

    def _run_children(self, children: "list[TaskTree]", blocker: "tl.Task", recurse: bool):
        for child in children:
            child_task = SingleTreeTask(self, child, recurse)
            if blocker:
                child_task.depends_on(blocker)

    def load_design(self):
        workdir = Path(self.scycfg.args.workdir)
        design_json = workdir / "common" / "model" / "design.json"
        with open(design_json, 'r') as f:
            design = json.load(f)

        assert len(design["modules"]) == 1, ("expected one top level module, " 
                                            "try setting the 'design_scope' option")
        self.scycfg.options.design_scope = design["modules"][0]["name"]

    def run_tree(self):
        common_task = self.scycfg.root
        workdir = Path(self.scycfg.args.workdir)
        (add_log, self.add_cells, self.enable_cells) = parse_common_sby(common_task, self.sbycfg, self.scycfg)

        # use sby to prepare input
        print(f"preparing input files")
        task_sby = workdir / "common.sby"

        with open(task_sby, 'w') as sbyfile:
            self.sbycfg.dump_common(sbyfile)

        sby_args = ["sby", "common.sby"]
        root_task = tl.Process(sby_args, cwd=workdir)
        root_task.events(tl.process.ExitEvent).handle(on_sby_exit)

        if self.scycfg.options.replay_vcd and not self.scycfg.options.design_scope:
            # load top level design name back from generated model
            design_task = tl.Task(on_run=self.load_design)
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
                            self.enable_cells[d["name"]]["enable"] = cell
                        elif d["pty"] == "scy_line":
                            line = int(d["val"], base=2)
                            if line:
                                self.add_cells[line]["cell"] = cell

            for name, vals in self.enable_cells.items():
                task_cell = self.enable_cells[name].copy()
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
        self.sbycfg.prep_shared(common_il)

        self._run_children(common_task.children, root_task, True)

    def run_task(self, task: TaskTree, recurse=True):
        task_trace = None
        workdir = Path(self.scycfg.args.workdir)
        setupmode = self.scycfg.args.setupmode
        root_task = None

        if task.uses_sby:
            # generate sby
            taskcfg = gen_sby(task, self.sbycfg, self.scycfg,
                              self.add_cells, self.enable_cells)
            task_sby = workdir / f"{task.dir}.sby"
            print(f"generating {task_sby}")
            with open(task_sby, 'w') as sbyfile:
                taskcfg.dump(sbyfile)
            task_trace = f"{task.tracestr}.{self.scycfg.options.trace_ext}"
            if not setupmode:
                # run sby
                sby_args = ["sby", "-f", f"{task.dir}.sby"]
                root_task = tl.Process(sby_args, cwd=workdir)
                root_task.events(tl.process.ExitEvent).handle(on_sby_exit)
                root_task.events(tl.process.OutputEvent).process(self.handle_cover_output)
        elif task.stmt == "trace":
            if self.scycfg.options.replay_vcd:
                raise SCYTreeException(task.stmt, "replay_vcd option incompatible with trace statement")
            if not task.is_leaf:
                raise SCYTreeException(task.children[0].stmt, "trace statement does not support children")
            if task.is_root or task.parent.is_common:
                raise SCYTreeException(task.full_line, "trace statement has nothing to trace")

            if not setupmode:
                # prepare yosys
                traces = gen_traces(task)

                # run yosys-witness to concatenate all traces
                yw_args = ["yosys-witness", "yw2yw"]
                for trace in traces:
                    yw_args.extend(trace.split())

                # now use yosys to replay trace and generate vcd
                yw_args.append(f"{task.name}.yw")
                yw_proc = tl.Process(yw_args, cwd=workdir)
                common_il = self.sbycfg.files[0].split()[-1]
                yosys_args = [
                    "yosys", "-p", 
                    f"read_rtlil {common_il}; sim -hdlname -r {task.name}.yw -vcd {task.name}.vcd"
                ]
                yosys_proc = tl.Process(yosys_args, cwd=workdir)
                yosys_proc.depends_on(yw_proc)
        elif task.stmt == "append":
            if self.scycfg.options.replay_vcd:
                raise SCYTreeException(task.stmt, "replay_vcd option incompatible with append statement")
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
            # this shouldn't happen since an unrecognised statement should have been caught by the tree parse
            raise SCYTreeException(task.full_line, "unrecognised statement")

        # add traces to children
        task.update_children_traces(task_trace)
        task.update_children_enable_cells(recurse=False)            

        if recurse:
            self._run_children(task.children, root_task, recurse)
