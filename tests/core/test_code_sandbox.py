from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.code_sandbox import Policy, _as_path, _check_open


@pytest.fixture
def policy(tmp_path: Path) -> Policy:
    (tmp_path / "run").mkdir()
    (tmp_path / "shared").mkdir()
    return Policy(tmp_path / "run", [tmp_path / "shared"])


def test_policy_lets_code_read_shared_folders_and_its_own_folder(policy: Policy, tmp_path: Path) -> None:
    assert policy.may_read(tmp_path / "shared" / "budget.xlsx")
    assert policy.may_read(tmp_path / "run" / "chart.png")


def test_policy_keeps_code_out_of_everything_else(policy: Policy, tmp_path: Path) -> None:
    assert not policy.may_read(tmp_path / "private" / "diary.txt")
    assert not policy.may_read(tmp_path / "sharedish" / "x.txt")


def test_policy_lets_code_write_only_its_own_folder(policy: Policy, tmp_path: Path) -> None:
    assert policy.may_write(tmp_path / "run" / "out.csv")
    assert not policy.may_write(tmp_path / "shared" / "budget.xlsx")


def test_check_open_allows_reading_a_shared_file(policy: Policy, tmp_path: Path) -> None:
    _check_open(policy, (str(tmp_path / "shared" / "a.csv"), "r", os.O_RDONLY))


def test_check_open_blocks_writing_a_shared_file(policy: Policy, tmp_path: Path) -> None:
    with pytest.raises(PermissionError, match="Can only write"):
        _check_open(policy, (str(tmp_path / "shared" / "a.csv"), "w", os.O_WRONLY))


def test_check_open_spots_a_write_from_the_flags_alone(policy: Policy, tmp_path: Path) -> None:
    with pytest.raises(PermissionError):
        _check_open(policy, (str(tmp_path / "shared" / "a.csv"), None, os.O_RDWR | os.O_CREAT))


def test_check_open_blocks_reading_outside(policy: Policy, tmp_path: Path) -> None:
    with pytest.raises(PermissionError, match="Can only read"):
        _check_open(policy, (str(tmp_path / "secret.txt"), "r", os.O_RDONLY))


def test_as_path_ignores_file_descriptors() -> None:
    assert _as_path(3) is None


def test_as_path_resolves_relative_paths_against_the_current_folder(tmp_path: Path) -> None:
    previous = Path.cwd()
    os.chdir(tmp_path)
    try:
        assert _as_path("x.txt") == tmp_path / "x.txt"
    finally:
        os.chdir(previous)
