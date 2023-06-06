import pytest
import subprocess

# See also ../updn_cntr/test_updn_cntr.py
@pytest.fixture(scope="module")
def scy_exec(request: pytest.FixtureRequest):
    scy_dir = request.path.parent
    args = ["scy", "-f", "hpm-test.scy"]
    return subprocess.run(args, cwd=scy_dir, capture_output=True)

def test_runs(scy_exec: subprocess.CompletedProcess):
    scy_exec.check_returncode()
