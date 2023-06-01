from textwrap import dedent
from scy.scy_task_tree import TaskTree
import pytest

def get_tree_list(func, tree: TaskTree):
    return list(map(func, tree.traverse()))

def test_empty_tree():
    task_tree = TaskTree.from_string("")
    assert task_tree == None

@pytest.fixture(params=["from_string", "constructed"])
def mintree(request) -> TaskTree:
    if request.param == "from_string":
        return TaskTree.from_string(dedent("""\
            cover a:
                cover b:
                    cover c:
                cover d
        """))
    elif request.param == "constructed":
        a = TaskTree("a", "cover", 0)
        b = TaskTree("b", "cover", 1)
        c = TaskTree("c", "cover", 2)
        d = TaskTree("d", "cover", 3)
        a.add_child(b.add_child(c)).add_child(d)
        return a
    else:
        return None

def test_mintree_exists(mintree):
    assert mintree

@pytest.mark.parametrize("xfunc,expected", [
        ("x.stmt", ["cover"]*4),
        ("x.name", ["a", "b", "c", "d"]),
        ("x.depth", [0, 1, 2, 1]),
        ("x.line", [0, 1, 2, 3]),
        ("x.is_root", [True, False, False, False]),
        ("x.is_leaf", [False, False, True, True]),
        ("len(x)", [4, 2, 1, 1]),
        ("len(x.children)", [2, 1, 0, 0]),
        ("len(list(x.traverse()))", [4, 2, 1, 1]),
        ("x.is_runnable", [True]*4)
])
def test_mintree_vals(mintree: TaskTree, xfunc, expected: list):
    assert get_tree_list(lambda x: eval(xfunc), mintree) == expected

@pytest.mark.parametrize("amount,expected", [(1, [0, 0, 1, 0]),
                                             (-1, [1, 2, 3, 2])])
def test_mintree_reduce_depth(mintree: TaskTree, amount: int, expected: list):
    mintree.reduce_depth(amount)
    assert get_tree_list(lambda x: x.depth, mintree) == expected

@pytest.mark.parametrize("input_str,stmt,name,asgmt,body", [
        ("cover", None, None, None, None),
        ("cover a", None, None, None, None),
        ("cover a:\n", "cover", "a", None, ""),
        ("cover b:\nbody", "cover", "b", None, "body"),
        ("cover c\n", "cover", "c", None, ""),
        ("enable cell d e f:\nbody\n", "enable", "cell", "d e f", "body\n"),
        ("cover g:\n body\n cover h", "cover", "g", None, " body\n"),
])
def test_task_from_string(input_str, stmt, name, asgmt, body):
    task_tree = TaskTree.from_string(input_str)
    if stmt:
        assert task_tree
        assert task_tree.stmt == stmt
        assert task_tree.name == name
        assert task_tree.asgmt == asgmt
        assert task_tree.body == body
    else:
        assert not task_tree

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

@pytest.fixture
def enable_tree():
    a = TaskTree("a", "cover", 0)
    b = TaskTree("cell", "enable", 1, asgmt="b")
    c = TaskTree("c", "cover", 2, enable_cells={"b": {"lhs": "0"}})
    d = TaskTree("d", "cover", 3, body="enable e\n")
    a.add_child(b.add_child(c)).add_child(d)
    return a

def test_enable_tree_len(enable_tree):
    tree_lens = get_tree_list(lambda x: len(x.enable_cells), enable_tree)
    assert tree_lens == [0, 0, 1, 0]

@pytest.fixture(params=[("test", {"val": "zero"}),
                        ("b", {"rhs": "test"})])
def enable_tree_with_cell(request, enable_tree: TaskTree):
    name, cell = request.param
    enable_tree.add_or_update_enable_cell(name, cell)
    return (name, cell, enable_tree)

def test_enable_tree_with_cell(enable_tree_with_cell):
    name, enable_cell, enable_tree = enable_tree_with_cell
    assert enable_tree.enable_cells.get(name) == enable_cell

def test_enable_tree_with_cell_len(enable_tree_with_cell):
    _, _, enable_tree = enable_tree_with_cell
    tree_lens = get_tree_list(lambda x: len(x.enable_cells), enable_tree)
    assert tree_lens == [1, 0, 1, 0]

@pytest.mark.parametrize("recurse", [True, False])
def test_update_children_enable_cells_len(enable_tree_with_cell, recurse):
    name, _, enable_tree = enable_tree_with_cell
    enable_tree.update_children_enable_cells(recurse)
    tree_lens = get_tree_list(lambda x: len(x.enable_cells), enable_tree)
    if name == "b" or not recurse:
        assert tree_lens == [1, 1, 1, 1]
    else:
        assert tree_lens == [1, 1, 2, 1]
