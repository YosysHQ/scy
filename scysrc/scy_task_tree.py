def from_sequence(seq: "list[str]", L0: int = 0) -> "TaskTree":
    root = None
    for i in range(len(seq)):
        if "cover" in seq[i]:
            if root:
                return root.add_child(TaskTree.from_sequence(seq[i:], L0+i))
            root = TaskTree(name=seq[0].strip(": "), line=L0+i)
    return root

class TaskTree:
    def __init__(self, name: str, line: int, steps: int = -1, 
                 parent: "TaskTree" = None, children: "list[TaskTree]" = None):
        self.name = name
        self.line = line
        self.steps = steps
        self.parent = parent
        if children:
            self.children = children
        else:
            self.children = []

    def add_child(self, child: "TaskTree"):
        child.parent = self
        self.children.append(child)
        return self

    def is_root(self):
        return self.parent is None
    
    def is_leaf(self):
        return not self.children

    def __str__(self):
        strings: list[str] = [f"L{self.line} => {self.steps} {self.name}"]
        for child in self.children:
            strings += str(child).split('\n')
        return "\n ".join(strings)
    
    from_sequence = staticmethod(from_sequence)
