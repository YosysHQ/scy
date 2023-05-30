from yosys_mau.config_parser import (
    BoolValue,
    ConfigOptions,
    ConfigParser,
    Option,
    OptionsSection,
    StrSection,
    postprocess_section
)
from scy_task_tree import TaskTree

class SCYOptions(ConfigOptions):
    replay_vcd = Option(BoolValue(), default=False)

class SCYConfig(ConfigParser):
    options = OptionsSection(SCYOptions)
    @postprocess_section(StrSection())
    def sequence (self, sequence: str) -> TaskTree:
        return TaskTree.from_string(sequence)
    design = StrSection(default="")
    files = StrSection(default="")
    file = StrSection(default="").with_arguments()
    sby_options = StrSection(default="")
    engines = StrSection(default="smtbmc boolector\n")
