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
    try:
        return test["cover_stmts"]
    except KeyError:
        pass

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
    try:
        return test["sequence"]
    except KeyError:
        pass

    sequence = []
    regex = r"(\d+)"
    subst = r"cover cp_\g<0>:"
    for test in test["data"]:
        sequence.append(re.sub(regex, subst, test))
    return sequence

@pytest.mark.parametrize("test", [
        {"name": "test0", "data": ["4", " 12", " 14", "  12"]},
        {"name": "fixed_data", "sequence": ["123", "abc"],
                               "cover_stmts": ["", "blank"]}
], scope="class")
class TestFixturesClass:
    def test_sequence(self, test, sequence):
        if "sequence" in test:
            assert sequence is test["sequence"]
        else:
            assert sequence == ["cover cp_4:",
                                " cover cp_12:",
                                " cover cp_14:",
                                "  cover cp_12:"]

    def test_cover_stmts(self, test, cover_stmts):
        if "cover_stmts" in test:
            assert cover_stmts is test["cover_stmts"]
        else:
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
def scy_cfg(scy_dir: Path, base_cfg: "dict[str, list[str]]", sequence, cover_stmts, 
            test: "dict[str, str]"):
    if "mkdir" in test:
        new_dir = scy_dir / test["mkdir"]
        new_dir.mkdir()
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
def cmd_args(test: "dict[str, list[str]]"):
    args = test.get("args", [])
    if "error" in test:
        args.append("-E")
    return args

@pytest.mark.parametrize("test", [
        {"name": "pass", "data": ["1", " 2", "  3"],
                 "chunks": [1, 1, 1]},
        {"name": "pass_seq", "data": ["1", "2", "3"],
                 "chunks": [1, 2, 3]},
        {"name": "chunks", "data": ["2", " 7", "  9", "  6"],
                 "chunks": [2, 5, 2, 1]},
        {"name": "chunks_reset", "data": ["6", " 3", "  2", " 2"],
                 "chunks": [6, 3, 1, 3]},
        {"name": "simple", "data": ["4", " 12", " 14", "  12"]},
        {"name": "good_trace", "sequence": ["cover cp_4:", " trace now:"],
                 "data": ["4"]},
        {"name": "add_reverse", "sequence": ["cover cp_254:",
                                             " add assume reverse:",
                                             "  cover cp_253"],
                 "cover_stmts": ["\tif (!reset) begin",
                                 "\t\tcp_253: cover(count==253);",
                                 "\t\tcp_254: cover(count==254);",
                                 "\tend"],
                 "chunks": [2, 1]},
        {"name": "force_reset", "sequence": ["cover cp_4:", 
                                             " cover cp_3",
                                             "cover cp_3"],
                 "cover_stmts": ["\tno_reverse: assume (!reverse);"
                                 "\tif (!reset) begin",
                                 "\t\tcp_3: cover(count==3);",
                                 "\t\tcp_4: cover(count==4);",
                                 "\tend"],
                 "chunks": [4, 4, 3]},
        {"name": "no_forced_reset", "sequence": ["cover cp_4:", 
                                                 " disable no_reverse:",
                                                 "  cover cp_3",
                                                 " cover cp_3:",
                                                 "  disable no_reverse",
                                                 "cover cp_3"],
                 "cover_stmts": ["\tno_reverse: assume (!reverse);"
                                 "\tif (!reset) begin",
                                 "\t\tcp_3: cover(count==3);",
                                 "\t\tcp_4: cover(count==4);",
                                 "\tend"],
                 "chunks": [4, 1, 1, 3]},
        {"name": "good_dir", "data": ["1"],
                 "args": ["-f", "-d", "this_dir"], "mkdir": "this_dir"},
        {"name": "empty_tree", "sequence": ["cover cp_4", "", "cover cp_3"],
                 "data": ["4", "3"]},
        {"name": "tree_comment", "sequence": ["cover cp_4", "#comment", "cover cp_3"],
                 "data": ["4", "3"]},
], scope="class")
class TestComplexClass:
    def test_runs(self, scy_exec: subprocess.CompletedProcess):
        scy_exec.check_returncode()

    @pytest.mark.usefixtures("scy_exec")
    def test_files(self, test: "dict[str, str|list[str]]", scy_dir: Path, scy_cfg: Path):
        assert test["name"] in scy_dir.name
        if "sequence" in test:
            output_dir = scy_dir / scy_cfg.stem
            output_files = [f.name for f in output_dir.glob("*")]
            for stmt in test["sequence"]:
                if not stmt:
                    continue
                found_match = False
                name = stmt.split()[-1].strip(':')
                if "cover" in stmt:
                    match_str = f"{name}.sby"
                elif "trace" in stmt:
                    match_str = f"{name}.vcd"
                else:
                    continue
                for file in output_files:
                    if match_str in file:
                        found_match = True
                        break
                assert found_match, f"{match_str} not found in {output_files} for test {test['name']!r}"

    def test_chunks(self, test: "dict[str]", scy_chunks: "list[int]"):
        if "chunks" in test:
            assert scy_chunks == test["chunks"]

@pytest.mark.parametrize("test", [
        {"name":  "trace_root", "sequence": ["trace now:", "cover cp_4:"],
                                "data": ["4"],
                                "error": "nothing to trace"},
        {"name": "trace_child", "sequence": ["trace now:", " cover cp_4:"],
                                "data": ["4"],
                                "error": "trace statement does not support children"},
        {"name":  "bad_parent", "sequence": ["cover cp_1:", " cover cp_2"],
                                "data": [],
                                "error": "sby produced an error",},
        {"name":     "bad_seq", "sequence": ["123", "abc"],
                                "cover_stmts": ["", "//blank"],
                                "error": "bad sequence"},
        {"name":    "bad_seq2", "sequence": ["", ""],
                                "cover_stmts": ["", "//blank"],
                                "error": "no cover sequences"},
        {"name":  "fail_depth", "data": ["1", " 2", "  3", "  44"],
                                "error": "sby produced an error"},
        {"name":   "fail_data", "data": [], "error": "no cover sequences"},
        {"name":     "bad_dir", "data": ["1"],
                                "args": ["-d", "this_dir"], "mkdir": "this_dir",
                                "error": "use -f to overwrite the existing directory"},
        {"name":   "no_covers", "sequence": ["cover cp_1:", ""],
                                "data": [],
                                "error": "task produced no trace",
                                "code": 1},
], scope="class")
class TestErrorsClass:
    def test_runs(self, test: "dict[str, str | list]", scy_exec: subprocess.CompletedProcess):
        if "code" in test:
            assert scy_exec.returncode == test["code"]
        else:
            with pytest.raises(subprocess.CalledProcessError):
                scy_exec.check_returncode()

        stderr = bytes.decode(scy_exec.stderr)
        exception_regex = r"^(?P<e>.*): (?P<m>.*)$"
        exceptions = re.findall(exception_regex, stderr, flags=re.MULTILINE)

        found_exception = False
        for _, m in exceptions:
            if test["error"] in m:
                found_exception = True
                break

        assert found_exception, f"{test['error']} not found in {exceptions}"

@pytest.mark.parametrize("test", [
        {"name": "baseline", "data": ["1", " 2", "  3"],
                 "args": []},
        {"name": "dump_tree", "data": ["1", " 2", "  3"],
                 "args": ["--dumptree"]},
        {"name": "setup_mode", "data": ["1", " 2", "  3"],
                 "args": ["--setup"]},
], scope="class")
class TestArgsClass:
    def test_runs(self, test: "dict[str, str | list]", scy_exec: subprocess.CompletedProcess):
        scy_exec.check_returncode()
    
    @pytest.mark.usefixtures("scy_exec")
    def test_files(self, test: "dict[str, str|list[str]]", scy_dir: Path, scy_cfg: Path):
        output_dir = scy_dir / scy_cfg.stem
        if "--dumptree" in test["args"]:
            assert not output_dir.exists()
            return
        assert output_dir.exists()

    def test_output(self, test: "dict[str, str | list]", sequence: "list[str]", scy_exec : subprocess.CompletedProcess):
        scy_out = bytes.decode(scy_exec.stdout)
        if "--dumptree" in test["args"]:
            for stmt in sequence:
                assert stmt.strip(' :') in scy_out
            return
        for stmt in ["Chunks:"]:
            if "--setup" in test["args"]:
                assert stmt not in scy_out
            else:
                assert stmt in scy_out
