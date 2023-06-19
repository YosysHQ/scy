from argparse import Namespace as ns
import asyncio
from textwrap import dedent
import pathlib

import scy.scy_task_runner as scytr
from scy.scy_config_parser import SCYConfig
from scy.scy_sby_bridge import SBYBridge
import pytest

@pytest.fixture(params=["setup", "run"])
def scycfg_upcnt(tmp_path, request: pytest.FixtureRequest):
    contents = dedent("""
            [design]
            read -sv up_counter.sv
            prep -top up_counter

            [files]
            up_counter.sv

            [sequence]
            cover cp_7:
                cover cp_3
                cover cp_14:
                    cover cp_12

            [file cover_stmts.vh]
                if (!reset) begin
                    cp_3: cover(count==3);
                    cp_7: cover(count==7);
                    cp_12: cover(count==12);
                    cp_14: cover(count==14);
                end
    """)
    scycfg = SCYConfig(contents)
    scycfg.args = ns(workdir=tmp_path)
    scycfg.args.setupmode = request.param == "setup"
    return scycfg

@pytest.fixture
def sbycfg_upcnt(scycfg_upcnt):
    sbycfg = SBYBridge.from_scycfg(scycfg_upcnt)
    return sbycfg

@pytest.fixture
def scytr_upcnt(sbycfg_upcnt: SBYBridge, scycfg_upcnt: SCYConfig):
    return scytr.TaskRunner(sbycfg_upcnt, scycfg_upcnt, client=None)

def test_setup(scytr_upcnt: scytr.TaskRunner):
    scycfg = scytr_upcnt.scycfg
    root = scycfg.sequence[0]
    if scycfg.args.setupmode:
        p = asyncio.run(scytr_upcnt.run_task(root, recurse=True))
        assert p == [], "expected no processes to run"
        sby_files = [file.name for file in pathlib.Path(scycfg.args.workdir).glob("*.sby")]
        for task in root.traverse():
            if task.uses_sby:
                sby_files.remove(f"{task.dir}.sby")
        assert not sby_files
    else:
        with pytest.raises(AttributeError):
            # client=None, so this should fail
            asyncio.run(scytr_upcnt.run_task(root))
