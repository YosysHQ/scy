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
from scy_task_tree import TaskTree

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
    def sequence (self, sequence: str) -> TaskTree:
        return TaskTree.from_string(sequence)
    design = StrSection(default="")
    engines = StrSection(default="smtbmc boolector\n")
    fallback = RawSection(all_sections=True)
