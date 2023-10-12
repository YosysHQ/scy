from __future__ import annotations

import os
import pathlib
from typing import Any

import pytest
from scy.scy_sby_bridge import SBYBridge


@pytest.fixture(
    params=[
        {},
        {"bad data": "test"},
        {"bad data": "a\nb\n\n", "good data": ["a", "b", ""]},
        {"bad data": None, "good data": []},
        {"options": ["a on", "b off"]},
        {"script": ["pass"]},
        {"files": ["test.scy", "a.b"]},
        {"file a.b": [""], "other": [""]},
    ]
)
def init_data(request: pytest.FixtureRequest) -> dict[str, Any]:
    return request.param


@pytest.fixture
def sbybridge(init_data) -> SBYBridge:
    return SBYBridge(init_data)


def test_bridge_init(init_data: dict[str, Any], sbybridge: SBYBridge):
    if "bad data" in init_data.keys():
        assert sbybridge.data != init_data
        if "good data" in init_data.keys():
            assert sbybridge.data["bad data"] == init_data["good data"]
    else:
        assert sbybridge.data == init_data


@pytest.mark.parametrize("key", ["options", "script", "files"])
def test_bridge_init_named(key: str, init_data: dict[str, Any], sbybridge: SBYBridge):
    if key in init_data.keys():
        assert init_data[key] == getattr(sbybridge, key)
    else:
        assert not getattr(sbybridge, key)


def test_bridge_prep_shared(init_data: dict[str, Any], sbybridge: SBYBridge):
    sbybridge.prep_shared("common.il")
    assert "skip_prep on" in sbybridge.options
    for key in init_data.keys():
        if key in ["script", "files"]:
            assert init_data[key][0] not in getattr(sbybridge, key)
        elif "file" in key:
            with pytest.raises(KeyError):
                sbybridge.data[key]


abs_dir = os.path.abspath(os.path.curdir)
path_dir = pathlib.Path(abs_dir)
path_up = pathlib.Path("..")


@pytest.mark.parametrize(
    "pre,ofs,post",
    [
        (
            ["a.b", os.path.join("b", "c"), abs_dir],
            "..",
            [path_up / "a.b", path_up / "b" / "c", abs_dir],
        ),
        (["a.b", abs_dir], abs_dir, [path_dir / "a.b", abs_dir]),
    ],
)
def test_bridge_fix_paths(pre: list[str], ofs: str, post: list[str]):
    sbybridge = SBYBridge()
    sbybridge.files = pre

    sbybridge.fix_relative_paths(ofs)

    for a, b in zip(sbybridge.files, post):
        assert a == str(b)


# TODO: test SBYBridge.dump() and SBYBridge.dump_common()
