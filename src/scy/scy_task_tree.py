from typing import Iterable
from yosys_mau import source_str
from yosys_mau.source_str import (
    re,
    SourceStr
)

def from_string(string: "SourceStr | str", L0: int = 0, depth: int = 0):
    if not isinstance(string, SourceStr):
        string = source_str.from_content(string, "dev/null")
    nest_regex = r"^(?P<ws>[ \t]*)(.+(\r?\n((?P=ws)[ \t]+.*|$))*)"
    tree_list: "list[TaskTree | str] | TaskTree" = []
    for tree in re.finditer(nest_regex, string, flags=re.MULTILINE):
        tree_str = tree.group()
        stmt_regex = r"^(?P<ws>\s*)(?P<stmt>cover|append|trace|add|disable|enable) "\
                    r"(?P<name>\S+?)( (?P<asgmt>.*?)|)(:\n(?P<body>.*)|:?\n|:?$)"
        m = re.search(stmt_regex, tree_str, flags=re.DOTALL)
        if not m: # no statement
            tree_list.append(tree_str)
            continue

        d = m.groupdict()
        # check for standalone body statements
        if d['stmt'] in ["enable", "disable"] and not d['body']:
            tree_list.append(tree_str)
            continue

        # if we're dealing with a source_str we can get the source line directly from it
        source_map = source_str.source_map(d['stmt'])
        span = source_map.spans[0]
        start_line, _ = span.file.text_position(span.file_start)
        line = start_line

        # otherwise continue recursively
        root = TaskTree(name=d['name'], stmt=d['stmt'], line=line, depth=depth,
                        asgmt=d.get('asgmt', None), full_line=tree_str.splitlines()[0])

        if d['body']:
            root.add_children(from_string(d['body']))

        tree_list.append(root)

    return tree_list

def make_common(children: "list[TaskTree|str]"=None):
    return TaskTree("", "common", 0, children=children)

class TaskTree:
    def __init__(self, name: str, stmt: str, line: int, steps: int = 0, depth: int = 0,
                 parent: "TaskTree" = None, children: "list[TaskTree|str]" = None,
                 body: str = "", asgmt: str = None, full_line: SourceStr = None,
                 enable_cells: "dict[str, dict[str, str]]" = None):
        self.name = name
        self.stmt = stmt
        self.line = line
        self.steps = steps
        self.depth = depth
        self.parent = parent
        self.children: "list[TaskTree|str]" = []
        self.body = body
        if children:
            self.add_children(children)
        self.traces = []
        self.asgmt = asgmt
        if enable_cells:
            self.enable_cells = enable_cells
        else:
            self.enable_cells = {}
        if full_line:
            self.full_line = full_line
        else:
            self.full_line = self.stmt

    def add_children(self, children: "list[TaskTree | str]"):
        for child in children:
            if isinstance(child, str):
                if self.body:
                    self.body = "\n".join([self.body, child])
                else:
                    self.body = child
            elif isinstance(child, TaskTree):
                self.add_child(child)
        return self

    def add_child(self, child: "TaskTree"):
        if child.parent:
            raise NotImplementedError("reassigning child's parent without unassigning other parent's child")
        child.parent = self
        self.children.append(child)
        child.depth = self.depth
        child.reduce_depth(-1)
        return self

    def add_enable_cell(self, name: str, cell: "dict[str, str]"):
        self.enable_cells[name] = cell

    def add_or_update_enable_cell(self, name: str, cell: "dict[str, str]"):
        try:
            self.enable_cells[name].update(cell)
        except KeyError:
            self.add_enable_cell(name, cell)

    def update_enable_cells_from_parent(self, recurse=False):
        for k, v in self.parent.enable_cells.items():
            try:
                self.enable_cells[k].update(v)
            except KeyError:
                self.enable_cells[k] = v.copy()
        if recurse:
            self.update_children_enable_cells(recurse)

    def update_children_traces(self, task_trace: str):
        for child in self.children:
            child.traces.extend(self.traces)
            if task_trace:
                child.traces.append(task_trace)

    def update_children_enable_cells(self, recurse=False):
        for child in self.children:
            child.update_enable_cells_from_parent(recurse)

    @property
    def is_root(self) -> bool:
        return self.parent is None

    @property
    def is_leaf(self) -> bool:
        return not self.children

    @property
    def is_common(self) -> bool:
        return self.stmt == "common"

    @property
    def uses_sby(self) -> bool:
        return self.stmt in ["cover", "common"]

    @property
    def makes_dir(self) -> bool:
        return self.uses_sby

    @property
    def is_runnable(self) -> bool:
        return self.stmt in ["cover", "trace"]

    @property
    def has_local_enable_cells(self) -> bool:
        return "enable" in self.body or "disable" in self.body

    @property
    def tracestr(self) -> str:
        if self.is_common:
            return "common"
        elif self.uses_sby:
            return f"trace{self.line:03d}"
        else:
            return self.parent.tracestr

    @property
    def linestr(self) -> str:
        return f"L{self.line:03d}_{0 if self.is_root else self.parent.line:03d}"

    def get_all_linestr(self) -> "list[str]":
        linestr = [f"L{self.line:03d}"]
        if self.is_root:
            return linestr
        else:
            return linestr + self.parent.get_all_linestr()

    @property
    def dir(self) -> str:
        if self.is_common:
            return "common"
        else:
            return f"{self.linestr}_{self.name}"

    def get_dir(self) -> str:
        if self.makes_dir:
            return self.dir
        else:
            return self.parent.get_dir()

    def get_asgmt(self):
        if self.asgmt:
            return {"lhs": self.asgmt}
        else:
            return None

    @property
    def start_cycle(self) -> int:
        if self.is_root:
            return 0
        else:
            return self.parent.stop_cycle

    @property
    def stop_cycle(self) -> int:
        start = self.start_cycle
        return start + self.steps

    def reduce_depth(self, amount: int = 1):
        self.depth = max(0, self.depth - amount)
        for child in self.children:
            child.reduce_depth(amount)

    def traverse(self, include_self = True) -> Iterable["TaskTree"]:
        if include_self:
            yield self
        for child in self.children:
            for task in child.traverse():
                yield task

    def as_str(self, recurse=False) -> str:
        strings: list[str] = [f"{self.linestr} => {self.stmt} {self.name}"]
        if self.asgmt:
            strings[0] += f" ({self.asgmt})"
        if self.body:
            for string in self.body.split('\n'):
                if string:
                    strings.append(string)
        if recurse:
            for child in self.children:
                strings += child.as_str(recurse).split('\n')
        return "\n ".join(strings)

    def __str__(self):
        return self.as_str(True)

    def __len__(self):
        length = 1
        for child in self.children:
            length += len(child)
        return length

    from_string = staticmethod(from_string)
    make_common = staticmethod(make_common)
