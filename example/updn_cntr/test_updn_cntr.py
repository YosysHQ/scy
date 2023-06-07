import pytest
import re
import subprocess
import shutil
from pathlib import Path

# example up_counter.scy
"""[design]
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
"""

@pytest.fixture(scope="class")
def base_cfg() -> "dict[str, list[str]]":
    return {"design":   ["read -sv up_counter.sv",
                         "prep -top up_counter"],
            "files":    ["up_counter.sv"]}

@pytest.fixture(scope="class")
def cover_stmts(test):
    counts = set()
    for test in test["data"]:
        counts.add(int(test.strip()))
    cover_stmts = ["\tif (!reset) begin"]
    for count in counts:
        cover_stmts.append(f"\t\tcp_{count}: cover(count=={count});")
    cover_stmts.append("\tend")

    return cover_stmts

@pytest.fixture(scope="class")
def sequence(test):
    sequence = []
    regex = r"(\d+)"
    subst = r"cover cp_\g<0>:"
    for test in test["data"]:
        sequence.append(re.sub(regex, subst, test))
    return sequence

@pytest.mark.parametrize("test", [
        {"name": "test0", "data": ["4", " 12", " 14", "  12"]},
], scope="class")
class TestFixturesClass:
    def test_sequence(self, sequence):
        assert sequence == ["cover cp_4:",
                            " cover cp_12:",
                            " cover cp_14:",
                            "  cover cp_12:"]

    def test_cover_stmts(self, test, cover_stmts):
        counts = [x.strip() for x in test["data"]]
        assert cover_stmts == ["\tif (!reset) begin",
                            f"\t\tcp_{counts[0]}: cover(count=={counts[0]});",
                            f"\t\tcp_{counts[1]}: cover(count=={counts[1]});",
                            f"\t\tcp_{counts[2]}: cover(count=={counts[2]});",
                            "\tend"]

@pytest.fixture(scope="class")
def scy_dir(tmp_path_factory: pytest.TempPathFactory, test, request: pytest.FixtureRequest):
    test_dir = tmp_path_factory.mktemp(test["name"], numbered=False)
    src_dir = request.path.parent / "up_counter.sv"
    shutil.copy(src_dir, test_dir)
    return test_dir

@pytest.fixture(scope="class")
def scy_cfg(scy_dir, base_cfg: "dict[str, list[str]]", sequence, cover_stmts):
    test_cfg = base_cfg.copy()
    test_cfg["sequence"] = sequence
    test_cfg["file cover_stmts.vh"] = cover_stmts
    cfg = Path("config.scy")
    with open(scy_dir / cfg, mode="w") as f:
        for k, v in test_cfg.items():
            f.write(f"[{k}]\n")
            f.write("\n".join(v))
            f.write("\n\n")
    return cfg

@pytest.fixture(scope="class")
def cmd_args():
    return []

@pytest.mark.parametrize("test", [
        {"name": "pass", "data": ["1", " 2", "  3"], "chunks": [1, 1, 1]},
        {"name": "chunks", "data": ["2", " 7", "  9", "  6"], "chunks": [2, 5, 2, 1]},
        {"name": "chunks_reset", "data": ["6", " 3", "  2", " 2"], "chunks": [6, 3, 1, 3]},
        {"name": "fail_depth", "data": ["1", " 2", "  3", "  44"], "failure": "sby"},
        {"name": "fail_data", "data": [], "failure": "scy"},
], scope="class")
class TestExecClass:
    def test_runs(self, test: "dict[str]", scy_exec: subprocess.CompletedProcess):
        failure = test.get("failure")
        if failure == "sby":
            assert scy_exec.returncode
        elif failure == "scy":
            assert scy_exec.returncode
        else:
            scy_exec.check_returncode()

    @pytest.mark.usefixtures("scy_exec")
    def test_files(self, test: "dict[str]", scy_dir: Path, scy_cfg: Path):
        assert test["name"] in scy_dir.name
        output_dir = scy_dir / scy_cfg.stem
        output_files = [f.name for f in output_dir.glob("*.sby")]
        for count in test["data"]:
            found_match = False
            match_str = f"cp_{count.strip()}"
            for file in output_files:
                if match_str in file:
                    found_match = True
                    break
            assert found_match, f"{match_str} not found in {output_files}"

    def test_chunks(self, test: "dict[str]", scy_chunks: "list[int]"):
        if test.get("chunks"):
            assert scy_chunks == test["chunks"]
