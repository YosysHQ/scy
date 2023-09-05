#!/usr/bin/env python3

import argparse
import os
from pathlib import Path
import shutil
from scy.scy_config_parser import SCYConfig, SCY_arg_parser
from scy.scy_sby_bridge import SBYBridge, SBYException
from scy.scy_task_runner import (
    SCYRunnerContext,
    SCYTaskContext,
    dump_trace,
    run_tree
)
from scy.scy_task_tree import TaskTree
from yosys_mau import source_str
import yosys_mau.task_loop as tl
from yosys_mau.task_loop import (
    LogContext,
    log,
    log_warning,
    log_exception,
    logging
)
import yosys_mau.task_loop.job_server as job

LogContext.app_name = "SCY"

class SCYTask():
    def __init__(self, args: "argparse.Namespace | None" = None):
        self.args = args
        self.localdir = False
        self.failed_tree = None

    def parse_scyfile(self):
        scy_source = source_str.read_file(self.args.scyfile)
        scycfg = SCYConfig(scy_source)
        scycfg.args = self.args
        with tl.root_task().as_current_task():
            SCYRunnerContext.scycfg = scycfg

    def display_tree(self):
        for seq in SCYRunnerContext.scycfg.sequence:
            if isinstance(seq, TaskTree):
                print(seq)

    def gen_workdir(self):
        try:
            os.makedirs(self.args.workdir)
        except FileExistsError:
            if self.args.force:
                shutil.rmtree(self.args.workdir, ignore_errors=True)
                os.makedirs(self.args.workdir)
            else:
                raise RuntimeError(f"directory '{self.args.workdir}' already exists, use -f to overwrite the existing directory.",)

    def prep_sby(self):
        sbycfg = SBYBridge.from_scycfg(SCYRunnerContext.scycfg)
        if self.localdir:
            sbycfg.fix_relative_paths("..")
        else:
            scy_path = Path(self.args.scyfile).absolute().parent
            sbycfg.fix_relative_paths(scy_path)
        with tl.root_task().as_current_task():
            SCYRunnerContext.sbycfg = sbycfg
            SCYRunnerContext.task_steps = {}

        # add common sby generation task
        SCYRunnerContext.scycfg.root = TaskTree.make_common(children=SCYRunnerContext.scycfg.sequence)

    def display_stats(self):
        trace_tasks: "list[TaskTree]" = []
        log("Chunks:")
        for task in SCYRunnerContext.scycfg.root.traverse():
            if task.stmt == "trace":
                trace_tasks.append(task)
            if task.stmt not in ["append", "cover"]:
                continue
            task.steps = SCYRunnerContext.task_steps.get(f"{task.linestr}_{task.name}")
            if task.steps:
                steps_str = f"{task.steps:2}"
                cycles_str = f"{task.start_cycle:2} .. {task.stop_cycle:2}"
            elif task == self.failed_tree:
                steps_str = " 0"
                cycles_str = "FAILED  "
            else:
                steps_str = " 0"
                cycles_str = "ABORTED "
            chunk_str = " "*task.depth + f"L{task.line}"
            task_str = task.name if task.is_runnable else f"{task.stmt} {task.name}"
            log(f"  {chunk_str:6}  {cycles_str}  =>  {steps_str}  {task_str}")

        if trace_tasks:
            log("Traces:")
        for task in trace_tasks:
            try:
                cycles_str = f"{task.stop_cycle + 1} cycles"
                chunks = task.parent.get_all_linestr()
                chunks.sort()
                chunks_str = " ".join(chunks)
                log(f"  {task.name:12} {cycles_str} [{chunks_str}]")
            except TypeError:
                log(f"  {task.name:12} N/A")

    def trace_final(self, exc: BaseException):
        # Find last successful task
        while isinstance(exc.__cause__, tl.ChildFailed):
            exc = exc.__cause__

        if isinstance(exc, tl.ChildFailed) and isinstance(exc.__cause__.__cause__, SBYException):
            self.failed_tree = exc.task[SCYTaskContext].task
        else:
            tl.log_exception(exc, raise_error=True)

    async def run(self):
        if self.args.workdir is None:
            self.args.workdir = self.args.scyfile.split('.')[0]
            self.localdir = True

        # setup logging
        logging.start_logging()
        if self.args.logfile:
            logging.start_logging(self.args.logfile)
        if self.args.log_debug:
            logging.start_debug_event_logging(self.args.logfile)

        # parse scy file
        parse_task = tl.Task(self.parse_scyfile)

        # dump_tree skip
        if self.args.dump_tree:
            display_task = tl.Task(on_run=self.display_tree)
            display_task.depends_on(parse_task)
            display_task[LogContext].scope = "tasks"
            return

        # generate workdir
        dir_task = tl.Task(on_run=self.gen_workdir)

        # prepare sby files
        prep_task = tl.Task(on_run=self.prep_sby)
        prep_task.depends_on(parse_task)

        # prepare task tree
        tree_task = tl.Task(on_run=run_tree)
        tree_task.depends_on(prep_task)
        tree_task.depends_on(dir_task)
        tree_task[SCYTaskContext].task = None

        # setupmode skip
        if self.args.setupmode or self.args.dump_common:
            return

        # recover last task before failure
        tree_task.handle_error(handler=self.trace_final)
        try:
            await tree_task.finished
        except tl.TaskFailed as exc:
            if not SCYRunnerContext.scycfg.args.trace_final:
                tl.log_exception(exc)

        # prepare stats task
        display_task = tl.Task(on_run=self.display_stats)
        display_task[LogContext].scope = "stats"

        if SCYRunnerContext.scycfg.args.trace_final:
            final_trace = TaskTree.from_string("trace __final")[0]
            if tree_task.state == "failed":
                # add trace to recovered task
                tl.LogContext.scope = "final trace"
                final_task = self.failed_tree.parent
                tl.log_warning(f"dumping trace from last successful task {final_task.linestr!r} to '__final.vcd'")
                final_task.add_child(final_trace)
            else:
                # add trace to final task
                scycfg = SCYRunnerContext.scycfg
                common_task = scycfg.root
                all_tasks = list(common_task.traverse(include_self = True))
                all_tasks.reverse()
                for task in all_tasks:
                    if task.stmt != "cover":
                        continue
                    task.add_child(final_trace)
                    break
            # run final trace
            final_trace_task = dump_trace(final_trace, SCYRunnerContext.scycfg.args.workdir)
            display_task.depends_on(final_trace_task)

def main():
    # read args
    parser = SCY_arg_parser()
    args=parser.parse_args()

    # setup
    job.global_client(args.jobcount)

    # run SCY
    scy_task = SCYTask(args)
    try:
        tl.run_task_loop(scy_task.run)
    except Exception as e:
        if args.throw_err:
            import traceback
            traceback.print_exc()
        else:
            log_warning("run with -E to print full stacktrace")
        log_exception(e, raise_error=False)
        exit(1)

if __name__ == "__main__":
    main()
