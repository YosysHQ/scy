from argparse import Namespace as ns
from textwrap import dedent
import pathlib

import scy.scy_task_runner as scytr
from scy.scy_config_parser import SCYConfig
from scy.scy_sby_bridge import SBYBridge
import pytest

from scy.scy_task_tree import TaskTree

@pytest.fixture(params=["setup", "run"])
def scycfg_upcnt(tmp_path, request: pytest.FixtureRequest):
    contents = dedent("""
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

    """)
    scycfg = SCYConfig(contents)
    scycfg.args = ns(workdir=tmp_path)
    scycfg.args.setupmode = request.param == "setup"
    scycfg.args.jobcount = None
    return scycfg

@pytest.fixture
def sbycfg_upcnt(scycfg_upcnt):
    sbycfg = SBYBridge.from_scycfg(scycfg_upcnt)
    return sbycfg

@pytest.fixture
def scytr_upcnt(sbycfg_upcnt: SBYBridge, scycfg_upcnt: SCYConfig):
    return scytr.TaskRunner(sbycfg_upcnt, scycfg_upcnt)

@pytest.fixture
def scytr_upcnt_with_common(scytr_upcnt: scytr.TaskRunner):
    scycfg = scytr_upcnt.scycfg
    scycfg.root = TaskTree("", "common", 0)
    scycfg.root.add_children(scycfg.sequence)
    return scytr_upcnt

@pytest.fixture
def run_tree(scytr_upcnt_with_common: scytr.TaskRunner):
    scytr_upcnt_with_common.run_tree()

@pytest.mark.usefixtures("run_tree")
def test_tree_makes_sby(scytr_upcnt: scytr.TaskRunner):
    scycfg = scytr_upcnt.scycfg
    root = scycfg.root
    sby_files = [f.name for f in pathlib.Path(scycfg.args.workdir).glob("*.sby")]
    for task in root.traverse():
        if task.uses_sby:
            sby_files.remove(f"{task.dir}.sby")
    assert not sby_files

@pytest.mark.usefixtures("run_tree")
def test_tree_respects_setup(scytr_upcnt: scytr.TaskRunner):
    scycfg = scytr_upcnt.scycfg
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
