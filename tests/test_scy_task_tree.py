from textwrap import dedent
from scy.scy_task_tree import TaskTree
import pytest

def get_tree_list(func, tree: TaskTree):
    return list(map(func, tree.traverse()))

def test_empty_tree():
    task_tree = TaskTree.from_string("")
    assert task_tree == None

class TestMinimalTreeClass:
    task_tree = TaskTree.from_string(dedent("""\
        cover a:
            cover b:
                cover c
            cover d
    """))

    def test_mintree_exists(self):
        assert self.task_tree
    
    def test_mintree_len4(self):
        assert len(self.task_tree) == 4

    def test_mintree_stmts(self):
        stmts = get_tree_list(lambda x: x.stmt, self.task_tree)
        assert stmts == ["cover"]*4

    def test_mintree_names(self):
        names = get_tree_list(lambda x: x.name, self.task_tree)
        assert names == ["a", "b", "c", "d"]

    def test_mintree_depths(self):
        depths = get_tree_list(lambda x: x.depth, self.task_tree)
        assert depths == [0, 1, 2, 1]

    def test_mintree_root_or_leaf(self):
        root_or_leaf = get_tree_list(lambda x: "root" if x.is_root 
                                     else "leaf" if x.is_leaf
                                     else "none", self.task_tree)
        assert root_or_leaf == ["root", "none", "leaf", "leaf"]

def test_enable_stmt():
    task_tree = TaskTree.from_string(dedent("""\
        cover a:
            enable cell b:
                cover c
    """))

    assert len(task_tree) == 3
    
    stmts = get_tree_list(lambda x: x.stmt, task_tree)
    assert stmts == ["cover", "enable", "cover"]

    enable_task = task_tree.children[0]
    assert enable_task.stmt == "enable"
    assert enable_task.asgmt == "b"
    assert enable_task.name == "cell"

def test_enable_body():
    task_tree = TaskTree.from_string(dedent("""\
        cover a:
            enable cell b
            cover c
    """))

    assert len(task_tree) == 2
    assert task_tree.has_local_enable_cells
