from textwrap import dedent
from scy.scy_task_tree import TaskTree
import pytest

def get_tree_list(func, tree: TaskTree):
    return list(map(func, tree.traverse()))

def test_empty_tree():
    task_tree = TaskTree.from_string("")
    assert task_tree == None

@pytest.fixture
def mintree() -> TaskTree:
    return TaskTree.from_string(dedent("""\
        cover a:
            cover b:
                cover c
            cover d
    """))

def test_mintree_exists(mintree):
    assert mintree

@pytest.mark.parametrize("xfunc,expected", [("x.stmt", ["cover"]*4),
                                            ("x.name", ["a", "b", "c", "d"]),
                                            ("x.depth", [0, 1, 2, 1]),
                                            ("x.line", [0, 1, 2, 3]),
                                            ("x.is_root", [True, False, False, False]),
                                            ("x.is_leaf", [False, False, True, True]),
                                            ("len(x)", [4, 2, 1, 1])])
def test_mintree_vals(mintree: TaskTree, xfunc, expected: list):
    assert get_tree_list(lambda x: eval(xfunc), mintree) == expected

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
    assert task_tree.body.strip() == "enable cell b"
    assert task_tree.has_local_enable_cells

def test_tree_blank_line():
    task_tree = TaskTree.from_string(dedent("""\
        
        cover a
    """))

    assert len(task_tree) == 1
    assert task_tree.stmt == "cover"
    assert task_tree.line == 1

def test_bad_stmt():
    task_tree = TaskTree.from_string(dedent("""\
        help
    """))

    assert not task_tree

# This test might be less of a "does the code do what we want" 
#   and more "if the code changes, this test will fail"
def test_no_colon():
    task_tree = TaskTree.from_string(dedent("""\
        cover a
            cover b
    """))

    assert len(task_tree) == 1
    assert task_tree.name == "a"
