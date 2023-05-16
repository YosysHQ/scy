import re
from typing import Iterable

def from_string(string: str, L0: int = 0) -> "TaskTree | None":
    stmt_regex = r"^\s*(?P<stmt>cover) (?P<name>\S+?):?\n(?P<body>.*)"
    m = re.search(stmt_regex, string, flags=re.DOTALL)
    if not m: # no statement
        return None

    root = TaskTree(name=m.group('name'), line=L0)
    line = L0 + 1

    body_str = m.group('body')
    body_regex = r"(?P<ws>\s+).*?\n(?=(?P=ws)\S|$)"
    for m in re.finditer(body_regex, body_str, flags=re.DOTALL):
        child = from_string(m.group(0), line)
        if child:
            root.add_child(child)
        else:
            root.body += m.group(0)
        line += m.group(0).count('\n')

    return root

def from_sequence(seq: "list[str]", L0: int = 0) -> "TaskTree":
    root = None
    for i in range(len(seq)):
        if "cover" in seq[i]:
            if root:
                return root.add_child(TaskTree.from_sequence(seq[i:], L0+i))
            root = TaskTree(name=seq[0].strip(": "), line=L0+i)
        elif root and seq[i]:
            root.body += f"{seq[i]}\n"
    return root

class TaskTree:
    def __init__(self, name: str, line: int, steps: int = -1, 
                 parent: "TaskTree" = None, children: "list[TaskTree]" = None,
                 body: str = "", traces: "list[str]" = None):
        self.name = name
        self.line = line
        self.steps = steps
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

    def add_child(self, child: "TaskTree"):
        child.parent = self
        self.children.append(child)
        return self

    def is_root(self):
        return self.parent is None
    
    def is_leaf(self):
        return not self.children
    
    def get_tracestr(self):
        return f"trace{self.line:03d}.vcd"
    
    def get_linestr(self):
        return f"L{self.line:03d}_{0 if self.is_root() else self.parent.line:03d}"

    def traverse(self, include_self = True) -> Iterable["TaskTree"]:
        if include_self:
            yield self
        for child in self.children:
            for task in child.traverse():
                yield task

    def __str__(self):
        strings: list[str] = [f"{self.get_linestr} => {self.steps} {self.name}"]
        if self.body:
            strings += self.body.split('\n')[:-1]
        for child in self.children:
            strings += str(child).split('\n')
        return "\n ".join(strings)
    
    from_sequence = staticmethod(from_sequence)
    from_string = staticmethod(from_string)
