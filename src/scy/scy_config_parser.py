import argparse
from scy.scy_task_tree import TaskTree
from yosys_mau.config_parser import (
    BoolValue,
    ConfigOptions,
    ConfigParser,
    Option,
    OptionsSection,
    RawSection,
    StrSection,
    StrValue,
    postprocess_section
)
from yosys_mau.task_loop import log_warning
from yosys_mau.source_str import re, source_map

def SCY_arg_parser():
    parser = argparse.ArgumentParser(prog="scy")

    # input arguments
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
    parser.add_argument("--debug", action="store_true", dest="log_debug",
            help="log debug events")
    parser.add_argument("--checkerror", action="store_true", dest="check_error",
            help="enable rudimentary error checking to help with error messages from sub processes")
    parser.add_argument("--tracefinal", action="store_true", dest="trace_final",
            help="always dump complete trace for last successful task, even if an error occurred after")

    parser.add_argument("--logfile", type=argparse.FileType('w'), dest="logfile",
            help="name of file to log to")

    parser.add_argument('scyfile', metavar="<jobname>.scy",
            help=".scy file")
    return parser

class SCYOptions(ConfigOptions):
    design_scope = Option(StrValue(), default="")
    replay_vcd = Option(BoolValue(), default=False)
    sby_options = ""

    def validate_options(self):
        for option in self.options(unprocessed_only=True):
            self.sby_options += f"{option.name} {option.arguments}\n"
            self.mark_as_processed(option)
        return super().validate_options()

    @property
    def trace_ext(self) -> str:
        return "vcd" if self.replay_vcd else "yw"

class SCYConfig(ConfigParser):
    options = OptionsSection(SCYOptions)
    @postprocess_section(StrSection())
    def sequence (self, sequence: str) -> "list[TaskTree | str]":
        # give a warning if whitespace mixes spaces and tabs
        ws_regex = r"^(?P<ws>[ \t]*)"
        for line in re.finditer(ws_regex, sequence, flags=re.MULTILINE):
            src = line.group()
            if " " in src and "\t" in src:
                log_warning(f"mixed whitespace at {source_map(src)}")
        # parse tree
        tree_list = TaskTree.from_string(sequence)
        for tree in tree_list:
            if isinstance(tree, str) and tree.startswith("#"):
                continue
            assert isinstance(tree, TaskTree), "bad sequence section"
        assert tree_list, "no cover sequences found"
        return tree_list
    design = StrSection(default="")
    engines = StrSection(default="smtbmc boolector\n")
    fallback = RawSection(all_sections=True)

    def __init__(self, contents: str) -> None:
        super().__init__(contents)
        self.args: argparse.Namespace = None
        self.root: TaskTree = None
