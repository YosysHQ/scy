import pytest
import subprocess
import os
from pathlib import Path
from textwrap import dedent

def gen_cfg(name: str):
    config: "dict[str, list[str]]" = {
            "design": dedent("""
                # read source
                read -sv cover.sv wrapper.sv nerv.sv
                prep -flatten -nordff -top rvfi_testbench
                # remove testbench init assumption 
                delete c:$assume$rvfi_testbench.sv*
            """).splitlines(),
            "files": dedent("""
                ../checks/rvfi_macros.vh
                ../checks/rvfi_channel.sv
                ../checks/rvfi_testbench.sv
                ../checks/rvfi_cover_check.sv
                ../nerv/wrapper.sv 
                ../nerv/nerv.sv
                ../cover_stmts.vh
            """).splitlines(),
            "file defines.sv": dedent("""
                `define RISCV_FORMAL
                `define RISCV_FORMAL_NRET 1
                `define RISCV_FORMAL_XLEN 32
                `define RISCV_FORMAL_ILEN 32
                `define RISCV_FORMAL_CHECKER rvfi_cover_check
                `define RISCV_FORMAL_RESET_CYCLES 1
                `define RISCV_FORMAL_CHECK_CYCLE 10
                `define RISCV_FORMAL_CSR_MHPMCOUNTER3
                `define RISCV_FORMAL_CSR_MHPMEVENT3
                `define YOSYS // Hotfix for older Tabby CAD Releases
                `define NERV_RVFI
                `define NERV_FAULT
                `define RISCV_FORMAL_ALIGNED_MEM
                `define RISCV_FORMAL_MEM_FAULT
                `include "rvfi_macros.vh"
            """).splitlines(),
            "file cover.sv": dedent("""
                `include "defines.sv"
                `include "rvfi_channel.sv"
                `include "rvfi_testbench.sv"
                `include "rvfi_cover_check.sv"
            """).splitlines()
    }
    config["options"] = [
            "depth 10", 
            "replay_vcd off"
    ]
    if name == "reset_only.scy":
        config["sequence"] = [
            "cover checker_inst.cp_reset_done:",
            "  disable checker_inst.ap_noreset"
        ]
    elif name == "rewind.scy":
        config["sequence"] = dedent("""
        cover checker_inst.cp_reset_done:
            enable checker_inst.ap_noreset:
                disable checker_inst.ap_nowrite:
                    cover checker_inst.cp_hpmevent3:
                        cover checker_inst.cp_hpmcounter
                        append -3:
                            cover checker_inst.cp_hpmcounter
        """).splitlines()
    elif name == "2or3.scy":
        config["sequence"] = dedent("""
        cover checker_inst.cp_reset_done:
            enable checker_inst.ap_noreset:
                cover checker_inst.cp_hpmevent2:
                    disable checker_inst.ap_nowrite
                    cover checker_inst.cp_hpmcounter
                cover checker_inst.cp_hpmevent3:
                    disable checker_inst.ap_nowrite
                    cover checker_inst.cp_hpmcounter
        """).splitlines()
    elif name == "shortest.scy":
        config["design"].append("connect -port checker_inst.ap_noreset \\EN 1'b0")
        config["design"].append("connect -port checker_inst.ap_nowrite \\EN 1'b0")
        config["sequence"] = dedent("""
        cover checker_inst.cp_reset_done:
            cover checker_inst.cp_hpmcounter
        """).splitlines()
    return config

def write_cfg(root: Path, filename: Path, config: "dict[str, list[str]]"):
    with open(root / filename, mode="w") as f:
        for k, v in config.items():
            f.write(f"[{k}]\n")
            f.write("\n".join(v))
            f.write("\n\n")

@pytest.fixture(scope="class")
def scy_cfg(request: pytest.FixtureRequest, cfg: str):
    if "gen_tests" in cfg:
        name = cfg.split('/', maxsplit=1)[1]
        config = gen_cfg(name)
        filename = Path("gen_tests") / name
        write_cfg(request.path.parent, filename, config)
        return filename
    else:
        return cfg

@pytest.fixture(scope="class")
def cmd_args():
    return ["-f"]

@pytest.fixture(scope="class")
def scy_dir(request: pytest.FixtureRequest):
    return request.path.parent

@pytest.mark.parametrize("cfg", [
        "hpm-test.scy",
        "gen_tests/reset_only.scy",
        "gen_tests/rewind.scy",
        "gen_tests/2or3.scy",
        "gen_tests/shortest.scy",
], scope="class")
class TestHPMClass:
    def test_runs(self, scy_exec: subprocess.CompletedProcess):
        scy_exec.check_returncode()

    def test_chunks(self, cfg, scy_chunks):
        if "gen_tests" in cfg:
            name = cfg.split('/', maxsplit=1)[1]
            chunks = {
                "reset_only.scy": [2],
                "rewind.scy": [2, 3, 5, 4],
                "2or3.scy": [2, 3, 3, 3, 5],
                "shortest.scy": [2, 4],
            }
            assert scy_chunks == chunks[name]
            
