from __future__ import annotations

import os
import subprocess
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
        assert _as_path("x.txt") == tmp_path.resolve() / "x.txt"
    finally:
        os.chdir(previous)


def _junction(link: Path, target: Path) -> None:
    created = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
    if created.returncode != 0:
        pytest.skip("This PC won't create a junction")


def test_a_junction_out_of_a_shared_folder_is_not_readable_or_writable(tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    shared = tmp_path / "shared"
    scratch = tmp_path / "scratch"
    secret.mkdir()
    shared.mkdir()
    scratch.mkdir()
    (secret / "note.txt").write_text("hidden", encoding="utf-8")
    (shared / "ok.txt").write_text("ok", encoding="utf-8")
    link = shared / "link"
    _junction(link, secret)
    policy = Policy(scratch, [shared])

    assert policy.may_read(_as_path(shared / "ok.txt"))
    assert policy.may_write(_as_path(scratch / "out.txt"))
    assert not policy.may_read(_as_path(link / "note.txt"))
    assert not policy.may_write(_as_path(link / "new.txt"))
