from textwrap import dedent
from scy.scy_task_tree import TaskTree
import pytest

def first_tree_from_string(input_str: str) -> "TaskTree | str":
    return TaskTree.from_string(input_str)[0]

def get_tree_list(func, tree: TaskTree):
    return list(map(func, tree.traverse()))

def test_empty_tree():
    task_tree = TaskTree.from_string("")
    assert not task_tree

@pytest.fixture(params=["from_string", "constructed"])
def mintree(request) -> "TaskTree | str":
    if request.param == "from_string":
        return first_tree_from_string(dedent("""\
            cover a:
                cover b:
                    cover c:
                cover d
        """))
    elif request.param == "constructed":
        a = TaskTree("a", "cover", 1)
        b = TaskTree("b", "cover", 2)
        c = TaskTree("c", "cover", 3)
        d = TaskTree("d", "cover", 4)
        a.add_children([b.add_child(c), d])
        return a
    else:
        return ""

def test_mintree_exists(mintree):
    assert mintree

@pytest.mark.parametrize("xfunc,expected", [
        ("x.stmt", ["cover"]*4),
        ("x.name", ["a", "b", "c", "d"]),
        ("x.depth", [0, 1, 2, 1]),
        ("x.line", [1, 2, 3, 4]),
        ("x.is_root", [True, False, False, False]),
        ("x.is_leaf", [False, False, True, True]),
        ("len(x)", [4, 2, 1, 1]),
        ("len(x.children)", [2, 1, 0, 0]),
        ("len(list(x.traverse()))", [4, 2, 1, 1]),
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
        ("cover a", "cover", "a", None, ""),
        ("cover a:\n", "cover", "a", None, ""),
        ("cover b:\n body", "cover", "b", None, " body"),
        ("cover c\n", "cover", "c", None, ""),
        ("enable cell d e f:\n body\n", "enable", "cell", "d e f", " body\n"),
        ("cover g:\n body\n cover h", "cover", "g", None, " body"),
        ("trace this\n", "trace", "this", None, ""),
        ("trace\n", None, None, None, None),
        #("add assume\n", None, None, None, None),
        ("add assume a b c\n", "add", "assume", "a b c", ""),
        ("enable no body:\n", None, None, None, None),
        ("enable with body:\n ", "enable", "with", "body", " "),
        ("disable that:\n ", "disable", "that", None, " "),
])
def test_task_from_string(input_str, stmt, name, asgmt, body):
    task_tree = first_tree_from_string(input_str)
    if stmt:
        assert isinstance(task_tree, TaskTree)
        assert task_tree.stmt == stmt
        assert task_tree.name == name
        assert task_tree.asgmt == asgmt
        assert task_tree.body == body
    else:
        assert isinstance(task_tree, str)

def test_enable_stmt():
    task_tree = first_tree_from_string(dedent("""\
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
    task_tree = first_tree_from_string(dedent("""\
        cover a:
            enable cell b
            cover c
    """))
    print(task_tree)
    assert len(task_tree) == 2
    assert task_tree.body.strip() == "enable cell b"
    assert task_tree.has_local_enable_cells

@pytest.fixture
def tree_with_blank():
    return first_tree_from_string(dedent("""\

        cover a
    """))

def test_tree_with_blank_len(tree_with_blank: TaskTree):
    assert len(tree_with_blank) == 1

def test_tree_with_blank_stmt(tree_with_blank: TaskTree):
    assert tree_with_blank.stmt == "cover"

def test_tree_with_blank_line(tree_with_blank: TaskTree):
    assert tree_with_blank.line == 2

def test_bad_stmt():
    task_tree = first_tree_from_string(dedent("""\
        help
    """))

    assert isinstance(task_tree, str)

@pytest.fixture
def no_colon():
    return TaskTree.from_string(dedent("""\
        cover a
            cover b
    """))

def test_no_colon_len(no_colon):
    assert len(no_colon) == 1

def test_no_colon_tree_len(no_colon):
    task_tree = no_colon[0]
    assert len(task_tree) == 1

def test_no_colon_name(no_colon):
    task_tree = no_colon[0]
    assert task_tree.name == "a"

@pytest.fixture(params=[
    {"input_str": "cover a:\n cover b:\n\tcover c:",
     "expected_lens": [3, 1, 1]},
    {"input_str": "cover a:\n cover b:\n\t cover c:",
     "expected_lens": [3, 1, 1]},
    {"input_str": "cover a:\n cover b:\n\t trace c",
     "expected_lens": [3, 1, 1]},
])
def mixed_spacing_input(request):
    return request.param

@pytest.fixture
def mixed_spacing_tree(mixed_spacing_input):
    return TaskTree.from_string(mixed_spacing_input["input_str"])

def test_mixed_spacing(mixed_spacing_input, mixed_spacing_tree):
    expected = mixed_spacing_input["expected_lens"]
    actual = get_tree_list(len, mixed_spacing_tree[0])
    assert actual == expected

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

@pytest.fixture(params=[
        {"input_str": dedent("""\
                                cover a:
                                    cover b
                                cover c:
                                    cover d
                            """),
         "len": 2, "trees": 2},
        {"input_str": "cover a\ncover b\ncover c",
         "len": 3, "trees": 3},
        {"input_str": "\ncover a\n cover b",
         "len": 1, "trees": 1},
        {"input_str": "cover a:\n cover b\n\ncover c",
         "len": 2, "trees": 2},
        {"input_str": "cover a\nempty\ncover b",
         "len": 3, "trees": 2},
        {"input_str": "\n\n\n",
         "len": 0, "trees": 0},
        {"input_str": "\n \n  \n",
         "len": 1, "trees": 0}, # this one could (should?) be 0 instead
])
def multi_root_input(request):
    return request.param

@pytest.fixture
def multi_root_tree(multi_root_input: "dict[str,str|int]"):
    return TaskTree.from_string(multi_root_input["input_str"])

def test_multi_root_len(multi_root_input: "dict[str,str|int]",
                        multi_root_tree: "list[TaskTree|str]"):
    expected_len = multi_root_input["len"]
    actual_len = len(multi_root_tree)
    assert actual_len == expected_len

def test_multi_root_trees(multi_root_input: "dict[str,str|int]",
                          multi_root_tree: "list[TaskTree|str]"):
    expected_trees = multi_root_input["trees"]
    actual_trees = len([x for x in multi_root_tree if isinstance(x, TaskTree)])
    assert actual_trees == expected_trees

@pytest.mark.parametrize("input_a,input_b,count", [
    ("cover a:\n\tcover b", "cover c:\n\tcover d", 4),
    ("cover a\ncover b", "cover c:\n\tcover d", 3),
    ("cover a:\n\tcover b", "cover c\ncover d", 4),
    ("cover a", "cover b\nstring\ncover c", 3),
])
def test_add_children(input_a: str, input_b: str, count: int):
    tree_a = first_tree_from_string(input_a)
    tree_a.add_children(TaskTree.from_string(input_b))
    assert len(tree_a) == count

@pytest.mark.parametrize([
     "input_str",           "prop",                     "expected",    "child"
    ], [
    ("cover a",             "is_root",                  True,           False),
    ("cover a:\n cover b",  "is_root",                  False,          True),
    ("cover a",             "is_leaf",                  True,           False),
    ("cover a:\n cover b",  "is_leaf",                  False,          False),
    ("cover a:\n cover b",  "is_leaf",                  True,           True),
    ("cover a",             "is_common",                False,          False),
    ("cover a",             "uses_sby",                 True,           False),
    ("trace a",             "uses_sby",                 False,          False),
    ("cover a",             "makes_dir",                True,           False),
    ("trace a",             "makes_dir",                False,          False),
    ("cover a",             "is_runnable",              True,           False),
    ("trace a",             "is_runnable",              True,           False),
    ("append a",            "is_runnable",              False,          False),
    ("cover a",             "has_local_enable_cells",   False,          False),
    ("cover a:\n enable a", "has_local_enable_cells",   True,           False),
    ("cover a:\n disable a","has_local_enable_cells",   True,           False),
    ("cover a",             "tracestr",                 "trace001",     False),
    ("cover a:\n cover b",  "tracestr",                 "trace002",     True),
    ("cover a:\n append 1", "tracestr",                 "trace001",     True),
    ("cover a:\n\n cover b","tracestr",                 "trace003",     True),
    ("cover a",             "linestr",                  "L001_000",     False),
    ("cover a:\n cover b",  "linestr",                  "L002_001",     True),
    ("cover a",             "dir",                      "L001_000_a",   False),
    ("cover a:\n cover b",  "dir",                      "L002_001_b",   True),
    ("cover a",             "children",                  [],            False),
    ("cover a",             "parent",                    None,          False),
    ("cover a:\n #comment", "body",                      " #comment",   False),
])
def test_statement_properties(input_str, prop, expected, child):
    task_tree = first_tree_from_string(input_str)
    if child:
        task_tree = task_tree.children[0]
    actual = getattr(task_tree, prop)
    assert actual == expected

@pytest.mark.parametrize([
     "input_str",           "func",         "expected",     "child"
    ], [
    ("cover a:\n trace b",  "get_dir",    "L001_000_a",   False),
    ("cover a:\n trace b",  "get_dir",    "L001_000_a",   True),
    ("cover a",             "get_asgmt",  None,           False),
    ("enable cell d e f:\n body\n",
                            "get_asgmt",  {"lhs": "d e f"},False),
])
def test_statement_callable(input_str, func, expected, child):
    task_tree = first_tree_from_string(input_str)
    if child:
        task_tree = task_tree.children[0]
    actual = getattr(task_tree, func)()
    assert actual == expected

@pytest.mark.parametrize([
     "func_or_prop",    "expected"
    ], [
    ("tracestr",        "common"),
    ("dir",             "common"),
    ("get_dir()",       "common"),
    ("as_str()",       "L000_000 => common "), # Should this be like this?
    ("uses_sby",        True),
    ("is_common",       True),
])
def test_common_tree(func_or_prop: str, expected):
    common_tree = TaskTree.make_common()
    if func_or_prop.endswith(")"):
        # function call
        actual = eval(f"common_tree.{func_or_prop}")
    else:
        # property
        actual = getattr(common_tree, func_or_prop)
    assert actual == expected

@pytest.fixture(params=[
    {"input_str": "cover a",
     "tree_lines": [1],
     "print_lines": (1, 1)},
    {"input_str": "\ncover a",
     "tree_lines": [2],
     "print_lines": (1, 1)},
    {"input_str": "cover a:\n cover b",
     "tree_lines": [1, 2],
     "print_lines": (1, 2)},
    {"input_str": "cover a:\n\n cover b",
     "tree_lines": [1, 3],
     "print_lines": (1, 2)},
    {"input_str": "cover a:\n \n cover b",
     "tree_lines": [1, 3],
     "print_lines": (1, 2)},
    {"input_str": "cover a:\n text\n cover b",
     "tree_lines": [1, 3],
     "print_lines": (2, 3)},
    {"input_str": "cover a:\n #comment\n cover b",
     "tree_lines": [1, 3],
     "print_lines": (2, 3)},
    {"input_str": "cover a:\n #comment1\n #comment2\n cover b",
     "tree_lines": [1, 4],
     "print_lines": (3, 4)},
    {"input_str": "enable cell d e f:\n body\n",
     "tree_lines": [1],
     "print_lines": (2, 2)}
])
def line_counts_input(request):
    return request.param

@pytest.fixture
def line_counts_tree(line_counts_input):
    return first_tree_from_string(line_counts_input["input_str"])

def test_tree_lines(line_counts_input: "dict[str, list[int]]", line_counts_tree: TaskTree):
    expected = line_counts_input["tree_lines"]
    actual = get_tree_list(lambda x: x.line, line_counts_tree)
    assert actual == expected

@pytest.mark.parametrize("recurse", [True, False])
def test_tree_print_lines(recurse: bool, line_counts_input: "dict[str, tuple[int,int]]", line_counts_tree: TaskTree):
    expected = line_counts_input["print_lines"][1 if recurse else 0]
    actual = line_counts_tree.as_str(recurse)
    print(line_counts_tree.body)
    assert len(actual.splitlines()) == expected

#TODO: get_all_linestr(), start_cycle and stop_cycle
