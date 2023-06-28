#!/usr/bin/env python3

import argparse
import os
import shutil
import sys
from scy.scy_config_parser import SCYConfig
from scy.scy_sby_bridge import SBYBridge
from scy.scy_task_runner import (
    SCYRunnerContext,
    run_tree
)
from scy.scy_task_tree import TaskTree
from scy.scy_exceptions import (
    SCYMissingTraceException,
)
from yosys_mau import source_str
import yosys_mau.task_loop as tl
from yosys_mau.task_loop import (
    LogContext,
    log,
    log_exception,
    logging
)
import yosys_mau.task_loop.job_server as job

LogContext.app_name = "SCY"

def parser_func():
    parser = argparse.ArgumentParser(prog="scy")

    # input arguments
    # mostly just a quick hack while waiting for common frontend
    parser.add_argument("-d", metavar="<dirname>", dest="workdir",
            help="set workdir name. default: <jobname>")
    parser.add_argument("-f", action="store_true", dest="force",
            help="remove workdir if it already exists")

    parser.add_argument("-E", action="store_true", dest="throw_err",
            help="throw an exception (incl stack trace) for most errors")
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
    return parser

class SCYTask():
    def __init__(self, args: "argparse.Namespace | None" = None):
        self.args = args

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
        sbycfg.fix_relative_paths("..")
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
            if not task.steps:
                err = SCYMissingTraceException(task.full_line, "task produced no trace")
                log_exception(err)
            chunk_str = " "*task.depth + f"L{task.line}"
            cycles_str = f"{task.start_cycle:2} .. {task.stop_cycle:2}"
            task_str = task.name if task.is_runnable else f"{task.stmt} {task.name}"
            log(f"  {chunk_str:6}  {cycles_str}  =>  {task.steps:2}  {task_str}")

        if trace_tasks:
            log("Traces:")
        for task in trace_tasks:
            cycles_str = f"{task.stop_cycle + 1:>2} cycles"
            chunks = task.parent.get_all_linestr()
            chunks.sort()
            chunks_str = " ".join(chunks)
            log(f"  {task.name:12} {cycles_str} [{chunks_str}]")

    def run(self):
        if self.args.workdir is None:
            self.args.workdir = self.args.scyfile.split('.')[0]

        # setup logging
        logging.start_logging()

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

        # setupmode skip
        if self.args.setupmode:
            return

        # output stats
        display_task = tl.Task(on_run=self.display_stats)
        display_task.depends_on(tree_task)
        display_task[LogContext].scope = "stats"

def main():
    # read args
    parser = parser_func()
    args=parser.parse_args()

    # setup
    job.global_client(args.jobcount)

    # run SCY
    scy_task = SCYTask(args)
    try:
        tl.run_task_loop(scy_task.run)
    except BaseException as e:
        if args.throw_err:
            import traceback
            traceback.print_exc()
        log_exception(e, raise_error=False)
        exit(1)

if __name__ == "__main__":
    main()
