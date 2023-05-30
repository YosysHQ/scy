from textwrap import dedent
from scy.scy_task_tree import TaskTree
import pytest

def test_empty_tree():
    task_tree = TaskTree.from_string("")
    assert task_tree == None

def test_minimal_tree():
    min_tree_str = dedent("""\
        cover a
            cover b
                cover c
            cover d
    """)


