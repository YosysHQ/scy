import re
import subprocess

import pytest


# Not sure how to solve this without requiring scy to be installed
@pytest.fixture(scope="class")
def scy_args(scy_cfg, cmd_args):
    args = ["scy"]
    args.extend(cmd_args)
    args.append(scy_cfg)
    return args


@pytest.fixture(scope="class")
def scy_exec(scy_dir, scy_args) -> subprocess.CompletedProcess:
    return subprocess.run(scy_args, cwd=scy_dir, capture_output=True)


@pytest.fixture(scope="class")
def scy_chunks(scy_exec: subprocess.CompletedProcess):
    scy_out = str(scy_exec.stdout, encoding="utf-8")
    regex = r"Chunks:\n(.*)"
    match = re.search(regex, scy_out, re.DOTALL)
    if match is None:
        return []
    chunk_str = match.group()
    chunk_regex = r"(\d+)  \S+$"
    return [int(x) for x in re.findall(chunk_regex, chunk_str, re.MULTILINE)]
