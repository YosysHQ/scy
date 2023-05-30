import re
from typing import Iterable

def from_string(string: str, L0: int = 0, depth: int = 0) -> "TaskTree | None":
    stmt_regex = r"^\s*(?P<stmt>cover|append|trace|add|disable|enable) "\
                 r"(?P<name>\S+?)( (?P<asgmt>.*?)|)(:\n(?P<body>.*)|\n)"
    m = re.search(stmt_regex, string, flags=re.DOTALL)
    if not m: # no statement
        return None

    d = m.groupdict()
    # check for standalone body statements
    if d['stmt'] in ["enable", "disable"] and not d['body']:
        return None
    # otherwise continue recursively
    root = TaskTree(name=d['name'], stmt=d['stmt'], line=L0, depth=depth,
                    asgmt=d.get('asgmt', None))
    line = L0 + 1

    body_str = m.group('body')
    body_regex = r"(?P<ws>\s+).*?\n(?=(?P=ws)\S|$)"
    if body_str:
        for m in re.finditer(body_regex, body_str, flags=re.DOTALL):
            child = from_string(m.group(0), line, depth+1)
            if child:
                root.add_child(child)
            else:
                root.body += m.group(0)
            line += m.group(0).count('\n')

    return root

class TaskTree:
    def __init__(self, name: str, stmt: str, line: int, steps: int = 0, depth: int = 0,
                 parent: "TaskTree" = None, children: "list[TaskTree]" = None,
                 body: str = "", traces: "list[str]" = None, asgmt: str = None,
                 enable_cells: "dict[str, dict[str, str]]" = None):
        self.name = name
        self.stmt = stmt
        self.line = line
        self.steps = steps
        self.depth = depth
        self.parent = parent
        if children:
            self.children = children
        else:
            self.children = []
        self.body = body
        if traces:
            self.traces = traces
        else:
            self.traces = []
        self.asgmt = asgmt
        if enable_cells:
            self.enable_cells = enable_cells
        else:
            self.enable_cells = {}

    def add_child(self, child: "TaskTree"):
        child.parent = self
        self.children.append(child)
        return self

    def is_root(self):
        return self.parent is None
    
    def is_leaf(self):
        return not self.children
    
    def is_runnable(self):
        return self.stmt in ["cover"]
    
    def has_local_enable_cells(self):
        return "enable" in self.body or "disable" in self.body
    
    def get_tracestr(self):
        if self.is_runnable():
            return f"trace{self.line:03d}"
        else:
            return self.parent.get_tracestr()
    
    def get_linestr(self):
        return f"L{self.line:03d}_{0 if self.is_root() else self.parent.line:03d}"
    
    def get_all_linestr(self):
        linestr = [f"L{self.line:03d}"]
        if self.is_root():
            return linestr
        else:
            return linestr + self.parent.get_all_linestr()
    
    def get_dir(self):
        if self.is_runnable():
            return f"{self.get_linestr()}_{self.name}"
        else:
            return self.parent.get_dir()

    def get_asgmt(self):
        if self.get_asgmt:
            return {"lhs": self.asgmt}
        else:
            return None
    
    def start_cycle(self) -> int:
        if self.is_root():
            return 0
        else:
            return self.parent.stop_cycle()

    def stop_cycle(self) -> int:
        start = self.start_cycle()
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

    def __str__(self):
        strings: list[str] = [f"{self.get_linestr()} => {self.stmt} {self.name}"]
        if self.asgmt:
            strings[0] += f" ({self.asgmt})"
        if self.body:
            strings += self.body.split('\n')[:-1]
        for child in self.children:
            strings += str(child).split('\n')
        return "\n ".join(strings)
    
    from_string = staticmethod(from_string)
