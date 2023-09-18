import copy
import os
from pathlib import Path
import re
from scy.scy_config_parser import SCYConfig
from scy.scy_exceptions import SCYSubProcessException
from scy.scy_task_tree import TaskTree
from yosys_mau import task_loop

class SBYException(SCYSubProcessException):
    def __init__(self, command: str, logfile=None, bestguess=None, typ: str = "UNKNOWN") -> None:
        super().__init__(command, logfile, bestguess)
        self.typ = typ

    @property
    def msg(self) -> str:
        return f"returned {self.typ}"

def from_scycfg(scycfg: SCYConfig):
    sbycfg = SBYBridge()
    sbycfg.add_section("options", scycfg.options.sby_options)
    sbycfg.add_section("script", scycfg.design)
    sbycfg.add_section("engines", scycfg.engines)

    for sect in scycfg.fallback:
        name = sect.name
        if sect.arguments: name += f" {sect.arguments}"
        sbycfg.add_section(name, sect.contents)
    return sbycfg

class SBYBridge():
    def __init__(self, data: "dict[str, list[str]]" = {}):
        self.data = {}
        for (name, contents) in data.items():
            self.add_section(name, contents)

    def add_section(self, name: str, contents: "str | list[str]"):
        if isinstance(contents, str):
            contents = contents.splitlines()
        try:
            self.data[name] = list(contents)
        except TypeError:
            self.data[name] = []

    @property
    def options(self) -> "list[str]":
        return self.data.get("options")

    @options.setter
    def options(self, contents: "str | list[str]"):
        self.add_section("options", contents)

    @property
    def script(self) -> "list[str]":
        return self.data.get("script")

    @script.setter
    def script(self, contents: "str | list[str]"):
        self.add_section("script", contents)

    @property
    def files(self) -> "list[str]":
        return self.data.get("files")

    @files.setter
    def files(self, contents: "str | list[str]"):
        self.add_section("files", contents)

    def fix_relative_paths(self, dir_prepend: str):
        if self.data["files"]:
            for i, s in enumerate(self.files):
                if s and not os.path.isabs(s):
                    self.files[i] = os.path.join(dir_prepend, s)

    def dump(self, sbyfile, skip_sections: "list[str]" = []):
        for (name, body) in self.data.items():
            if name in skip_sections:
                continue
            print(f"[{name}]", file=sbyfile)
            print("\n".join(body), file=sbyfile)

    def dump_common(self, sbyfile):
        old_options = self.data.get("options")
        options = old_options.copy()
        options.append("mode prep")
        self.options = options
        self.dump(sbyfile, skip_sections=["engines"])
        if old_options:
            self.options = old_options
        else:
            self.data.pop("options")

    def prep_shared(self, common_il: str):
        shared_options = ["mode cover",
                          "expect pass",
                          "skip_prep on"]
        try:
            self.options.extend(shared_options)
        except AttributeError:
            self.options = shared_options
        self.script = ["read_rtlil common_design.il"]
        self.files = [f"common_design.il {common_il}"]
        for key in list(self.data.keys()):
            if "file " in key:
                self.data.pop(key)

    def handle_error(self, event_task: task_loop.Process,
                     check_error: bool, failed_task: TaskTree) -> "Exception | None":
        task_loop.LogContext.scope += " SBY"
        event_cmd = " ".join(event_task.command)
        input_file = Path(event_task.command[-1])
        event_dir = Path(event_task.cwd)
        logfile: Path = (event_dir / input_file.stem / 'logfile.txt')
        return_code = event_task.returncode
        bestguess = []

        if return_code == 2:
            typ = "FAIL"
        elif return_code == 8:
            typ = "TIMEOUT"
        elif return_code == 16:
            typ = "ERROR"
        else:
            typ = "UNKNOWN"

        # open log file
        with open(logfile, "r") as f:
            log = f.read()

        # log summary
        regex = r"summary: (.*)"
        summary: "list[str]" = re.findall(regex, log, flags=re.MULTILINE)
        for msg in summary:
            task_loop.log_warning(msg)
            if check_error and 'unreached cover statements' in msg:
                bestguess.append(f"unreached cover statement for {failed_task.name!r}")

        # check reported error
        regex = r"(ERROR): (.*)"
        problems: "list[tuple[str, str]]" = re.findall(regex, log, flags=re.MULTILINE)
        for _, msg in problems:
            task_loop.log_error(msg, raise_error = False)
            if check_error and 'Shell command failed!' in msg:
                bestguess.append("may be missing vcd2fst")
            if check_error and 'selection contains 0 elements' in msg:
                bestguess.append(f"missing cover property for {failed_task.name!r}")

        task_loop.LogContext.scope = task_loop.LogContext.scope[0:-4]
        return SBYException(event_cmd, logfile, bestguess, typ)

    from_scycfg = staticmethod(from_scycfg)

def parse_common_sby(common_task: TaskTree, sbycfg: SBYBridge, scycfg: SCYConfig):
    assert common_task.is_common, "expected tree root to be common.sby generation"

    # preparse tree to extract cell generation
    add_cells: "dict[int, dict[str]]" = {}
    enable_cells: "dict[str, dict[str, str | bool]]" = {}
    def add_enable_cell(hdlname: str, stmt: str):
        enable_cells.setdefault(hdlname, {"disable": "1'b0"})
        enable_cells[hdlname][f"does_{stmt}"] = True

    for task in common_task.traverse():
        if task.stmt == "add":
            if task.name not in ["assert", "assume", "live", "fair", "cover"]:
                raise NotImplementedError(f"cell type {task.name!r} on line {task.line}")
            add_cells[task.line] = {"type": task.name}
            add_cells[task.line].update(task.get_asgmt())
        elif task.stmt in ["enable", "disable"]:
            add_enable_cell(task.name, task.stmt)
        elif task.body:
            for line in task.body.split('\n'):
                try:
                    stmt, hdlname = line.split()
                except ValueError:
                    continue
                if stmt in ["enable", "disable"]:
                    add_enable_cell(hdlname, stmt)

    # add cells to sby script
    add_log = None
    for (line, cell) in add_cells.items():
        sbycfg.script.extend([f"add -{cell['type']} {cell['lhs']} # line {line}",
                            f"setattr -set scy_line {line}  w:{cell['lhs']} %co c:$auto$add* %i"])
    for hdlname in enable_cells.keys():
        select = f"c:{hdlname} %ci:+[EN] c:{hdlname} %d"
        sbycfg.script.append(f"setattr -set scy_line 0 -set hdlname:{hdlname} 1 -set keep 1 {select}")
    if add_cells or enable_cells:
        add_log = "add_cells.log"
        sbycfg.script.append(f"tee -o {add_log} printattrs a:scy_line")
        add_log = Path(scycfg.args.workdir) / "common" / "src" / add_log

    return (add_log, add_cells, enable_cells)

def gen_sby(task: TaskTree, sbycfg: SBYBridge, scycfg: SCYConfig,
            add_cells: "dict[int, dict[str]]",
            enable_cells: "dict[str, dict[str, str | bool]]"):

    sbycfg = copy.deepcopy(sbycfg)

    if not task.is_root and not task.parent.is_common:
        # child nodes depend on parent
        parent = task.parent
        parent_trace = os.path.join(parent.get_dir(),
                                 "engine_0",
                                 f"trace0.{scycfg.options.trace_ext}")
        traces = [os.path.join(parent.get_dir(),
                               "src",
                               trace.split()[0]) for trace in task.traces[:-1]]
        sbycfg.files.extend(traces + [f"{parent.tracestr}.{scycfg.options.trace_ext} {parent_trace}"])

    # configure additional cells
    pre_sim_commands = []
    post_sim_commands = []
    for cell in add_cells.values():
        en_sig = '1' if cell["cell"] in task.enable_cells else '0'
        pre_sim_commands.append(f"connect -port {cell['cell']} \\EN 1'b{en_sig}")
    for hdlname in enable_cells.keys():
        task_cell = task.enable_cells.get(hdlname, None)
        if task.has_local_enable_cells:
            for line in task.body.split('\n'):
                if hdlname in line:
                    task_cell = enable_cells[hdlname].copy()
                    task_cell["status"] = line.split()[0]
                    break
        if task_cell:
            status = task_cell["status"]
            pre_sim_commands.append(f"connect -port {hdlname} \\EN {task_cell[status]}")
            if status == "enable":
                post_sim_commands.append(f"chformal -skip 1 c:{hdlname}")
    sbycfg.script.extend(pre_sim_commands)

    # replay prior traces and enable only relevant cover
    traces_script = []
    for trace in task.traces:
        if scycfg.options.replay_vcd:
            trace_scope = f" -scope {scycfg.options.design_scope}"
        else:
            trace_scope = ""
        traces_script.append(f"sim -w -r {trace}{trace_scope}")
    if task.stmt == "cover":
        traces_script.append(f"delete t:$cover c:{task.name} %d")
        traces_script.append(f"select -assert-count 1 t:$cover")
        sbycfg.script.extend(traces_script)
    else:
        raise NotImplementedError(task.stmt)
    sbycfg.script.extend(post_sim_commands)

    return sbycfg
