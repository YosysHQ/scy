from __future__ import annotations

import pathlib
from contextlib import nullcontext as does_not_raise
from textwrap import dedent

import pytest
import scy.scy_task_runner as scytr
import yosys_mau.task_loop as tl
from scy.scy_config_parser import SCY_arg_parser, SCYConfig
from scy.scy_exceptions import (
    SCYTreeError,
    SCYUnknownCellError,
    SCYUnknownStatementError,
    SCYValueError,
)
from scy.scy_sby_bridge import SBYBridge
from scy.scy_task_tree import TaskCell, TaskTree


class TaskRunner:
    def __init__(self, sbycfg: SBYBridge, scycfg: SCYConfig):
        self.sbycfg = sbycfg
        self.scycfg = scycfg
        self.add_cells: dict[int, dict[str, str]] = {}
        self.enable_cells: dict[str, TaskCell] = {}
        self.task_steps: dict[str, int] = {}

    def _prep_loop(self, recurse: bool):
        scytr.SCYTaskContext.recurse = recurse
        scytr.SCYRunnerContext.sbycfg = self.sbycfg
        scytr.SCYRunnerContext.scycfg = self.scycfg
        scytr.SCYRunnerContext.add_cells = self.add_cells
        scytr.SCYRunnerContext.enable_cells = self.enable_cells
        scytr.SCYRunnerContext.task_steps = self.task_steps

    def run_tree_loop(self):
        tl.run_task_loop(self._run_tree)

    def _run_tree(self):
        scytr.SCYRunnerContext.sbycfg = self.sbycfg
        scytr.SCYRunnerContext.scycfg = self.scycfg
        scytr.SCYRunnerContext.task_steps = self.task_steps
        scytr.run_tree()

    def run_task_loop(self, task: TaskTree, recurse=True):
        tl.run_task_loop(lambda: self._run_children([task], recurse))

    def _run_children(self, children: list[TaskTree], recurse: bool):
        self._prep_loop(recurse)
        scytr.run_children(children, None)


@pytest.fixture
def base_scycfg(tmp_path: pathlib.Path):
    contents = dedent(
        """
            [design]
            read -sv up_counter.sv
            prep -top up_counter

            [sequence]
            cover cp_7:
                cover cp_3
                cover cp_14:
                    cover cp_12

            [file up_counter.sv]
            module up_counter (
                input clock,
                input reset,
                input reverse,
                output [7:0] value
            );
                reg [7:0] count;

                assign value = count;

                initial begin
                    count = 0;
                end

                always @(posedge clock) begin
                    if (reset && reverse) begin
                        count = 8'h ff;
                    end else if (reset && !reverse) begin
                        count = 8'h 00;
                    end else if (!reset && reverse) begin
                        count = count-1;
                    end else /*(!reset && !reverse)*/ begin
                        count = count+1;
                    end

                    if (!reset) begin
                        cp_3: cover(count==3);
                        cp_7: cover(count==7);
                        cp_12: cover(count==12);
                        cp_14: cover(count==14);
                    end
                end


            endmodule

    """
    )
    scycfg = SCYConfig(contents)
    # use the arg parser to setup defaults more easily
    scycfg.args = SCY_arg_parser().parse_args(["-d", str(tmp_path), "dummy.scy"])
    return scycfg


@pytest.fixture(scope="function")
def scycfg(base_scycfg: SCYConfig, request: pytest.FixtureRequest):
    scycfg = base_scycfg
    try:
        assert isinstance(request.param, dict)
    except AttributeError:
        return scycfg
    for k, v in request.param.get("args", {}).items():
        setattr(scycfg.args, k, v)
    for k, v in request.param.get("options", {}).items():
        setattr(scycfg.options, k, v)
    return scycfg


@pytest.fixture
def sbycfg(scycfg: SCYConfig):
    sbycfg = SBYBridge.from_scycfg(scycfg)
    return sbycfg


@pytest.fixture
def scytr_upcnt(sbycfg: SBYBridge, scycfg: SCYConfig):
    return TaskRunner(sbycfg, scycfg)


@pytest.fixture
def scycfg_upcnt(base_scycfg: SCYConfig, request: pytest.FixtureRequest):
    base_scycfg.options.replay_vcd = request.param == "replay_vcd"
    base_scycfg.args.setupmode = request.param == "setup"
    return base_scycfg


@pytest.fixture
def scytr_upcnt_with_common(scytr_upcnt: TaskRunner):
    scycfg = scytr_upcnt.scycfg
    scycfg.root = TaskTree("", "common", 0)
    scycfg.root.add_children(scycfg.sequence)
    return scytr_upcnt


@pytest.fixture
def run_tree(scytr_upcnt_with_common: TaskRunner):
    scytr_upcnt_with_common.run_tree_loop()


@pytest.mark.usefixtures("run_tree")
@pytest.mark.parametrize(
    "scycfg",
    [
        ({"options": {"replay_vcd": True}}),
        ({"options": {"replay_vcd": False}}),
    ],
    indirect=True,
)
def test_tree_makes_sby(scytr_upcnt: TaskRunner):
    scycfg = scytr_upcnt.scycfg
    root = scycfg.root
    sby_files = [f.name for f in pathlib.Path(scycfg.args.workdir).glob("*.sby")]
    for task in root.traverse():
        if task.uses_sby:
            sby_files.remove(f"{task.dir}.sby")
    assert not sby_files


@pytest.mark.usefixtures("run_tree")
@pytest.mark.parametrize(
    "scycfg",
    [
        ({"args": {"setupmode": True}}),
        ({"args": {"setupmode": False}}),
    ],
    indirect=True,
)
def test_tree_respects_setup(scycfg: SCYConfig):
    root = scycfg.root
    sby_dirs = [f.name for f in pathlib.Path(scycfg.args.workdir).iterdir() if f.is_dir()]
    if scycfg.args.setupmode:
        assert "common" in sby_dirs
        sby_dirs.remove("common")
    else:
        for task in root.traverse():
            if task.makes_dir:
                assert task.dir in sby_dirs
                sby_dirs.remove(task.dir)
    assert not sby_dirs


def test_run_task(scytr_upcnt: TaskRunner):
    scytr_upcnt.sbycfg.options.append("mode cover")
    root_task = scytr_upcnt.scycfg.sequence[0]
    assert isinstance(root_task, TaskTree)
    scytr_upcnt.run_task_loop(root_task, recurse=False)


def test_run_task_nomode(scytr_upcnt: TaskRunner):
    try:
        scytr_upcnt.sbycfg.options.remove("mode cover")
    except ValueError:
        # nothing to remove
        pass
    root_task = scytr_upcnt.scycfg.sequence[0]
    if scytr_upcnt.scycfg.args.setupmode:
        assert isinstance(root_task, TaskTree)
        scytr_upcnt.run_task_loop(root_task, recurse=False)
    else:
        with pytest.raises(tl.TaskFailed):
            assert isinstance(root_task, TaskTree)
            scytr_upcnt.run_task_loop(root_task, recurse=False)


def run_task_loop_with_errors(scytr_upcnt: TaskRunner, task: TaskTree):
    try:
        scytr_upcnt.run_task_loop(task, False)
    except BaseException as e:
        # find root exception
        while e.__cause__:
            e = e.__cause__
        raise e


@pytest.mark.parametrize(
    "task,e_type,e_str",
    [
        (
            TaskTree("name", "stmt", 0),
            SCYUnknownStatementError,
            "unrecognised statement",
        ),
        (TaskTree("name", "append", 0), SCYTreeError, "cannot be root"),
        (TaskTree("name", "trace", 0), SCYTreeError, "cannot be root"),
        (TaskTree("name", "add", 0), SCYUnknownCellError, "attempted to add"),
        (TaskTree("name", "enable", 0), SCYUnknownCellError, "attempted to enable"),
    ],
)
def test_tr_with_stmt(scytr_upcnt: TaskRunner, task: TaskTree, e_type: type, e_str: str):
    with pytest.raises(SCYTreeError) as exc_info:
        run_task_loop_with_errors(scytr_upcnt, task)
    assert isinstance(exc_info.value, e_type), f"expected {e_type}, got {exc_info.type}"
    assert e_str in str(exc_info.value)


@pytest.mark.parametrize(
    "task,e_type,e_str",
    [
        (TaskTree("name", "append", 0), SCYTreeError, "expected parent task"),
        (TaskTree("name", "trace", 0), SCYTreeError, "requires common sby generation"),
    ],
)
def test_appended_task(scytr_upcnt: TaskRunner, task: TaskTree, e_type: type, e_str: str):
    task_tree = scytr_upcnt.scycfg.sequence[-1]
    assert isinstance(task_tree, TaskTree)
    task_tree.add_child(task)
    with pytest.raises(SCYTreeError) as exc_info:
        run_task_loop_with_errors(scytr_upcnt, task)
    assert isinstance(exc_info.value, e_type), f"expected {e_type}, got {exc_info.type}"
    assert e_str in str(exc_info.value)


def run_tree_loop_with_errors(scytr_upcnt: TaskRunner):
    try:
        scytr_upcnt.run_tree_loop()
    except BaseException as e:
        # find root exception
        while e.__cause__:
            e = e.__cause__
        raise e


@pytest.mark.parametrize(
    "task,scycfg,expectation",
    [
        (
            TaskTree("name", "append", 0),
            {"options": {"replay_vcd": True}},
            pytest.raises(SCYTreeError, match="replay_vcd option incompatible"),
        ),
        (
            TaskTree("name", "append", 0),
            {"options": {"replay_vcd": False}},
            pytest.raises(SCYValueError, match="must be integer literal"),
        ),
        (
            TaskTree("name", "trace", 0),
            {"options": {"replay_vcd": True}},
            pytest.raises(SCYTreeError, match="replay_vcd option incompatible"),
        ),
        (
            TaskTree("name", "trace", 0),
            {"options": {"replay_vcd": False}},
            does_not_raise(),
        ),
    ],
    indirect=["scycfg"],
)
def test_tree_with_appended(scytr_upcnt_with_common: TaskRunner, task: TaskTree, expectation):
    task_tree = scytr_upcnt_with_common.scycfg.sequence[-1]
    assert isinstance(task_tree, TaskTree)
    task_tree.add_child(task)
    with expectation:
        run_tree_loop_with_errors(scytr_upcnt_with_common)
