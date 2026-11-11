from __future__ import annotations

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from core.exceptions import ToolError
from core.file_tidy import FileTidier, clean_name, free_path


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "log" / "file_changes.jsonl"


@pytest.fixture
def tidier(log_path: Path) -> FileTidier:
    return FileTidier(log_path)


@pytest.fixture
def report(tmp_path: Path) -> Path:
    path = tmp_path / "share" / "report.pdf"
    path.parent.mkdir()
    path.write_text("report", encoding="utf-8")
    return path


def test_move_puts_file_in_new_folder(tidier: FileTidier, report: Path) -> None:
    change = tidier.move(report, report.parent / "Reports")

    assert change.destination == report.parent / "Reports" / "report.pdf"
    assert change.destination.read_text(encoding="utf-8") == "report"
    assert not report.exists()


def test_move_never_overwrites(tidier: FileTidier, report: Path) -> None:
    folder = report.parent / "Reports"
    folder.mkdir()
    (folder / "report.pdf").write_text("older", encoding="utf-8")

    change = tidier.move(report, folder)

    assert change.destination.name == "report (2).pdf"
    assert (folder / "report.pdf").read_text(encoding="utf-8") == "older"


def test_move_refuses_same_folder(tidier: FileTidier, report: Path) -> None:
    with pytest.raises(ToolError, match="already in"):
        tidier.move(report, report.parent)


def test_move_missing_file_is_explained(tidier: FileTidier, tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="doesn't exist"):
        tidier.move(tmp_path / "nope.txt", tmp_path / "x")


def test_move_folder_into_itself_is_refused(tidier: FileTidier, tmp_path: Path) -> None:
    folder = tmp_path / "Photos"
    folder.mkdir()

    with pytest.raises(ToolError):
        tidier.move(folder, folder / "Inner")

    assert tidier.last_change() is None


def test_move_locked_file_is_explained(tidier: FileTidier, report: Path, mocker: MockerFixture) -> None:
    mocker.patch("core.file_tidy.os.rename", side_effect=PermissionError)

    with pytest.raises(ToolError, match="in use"):
        tidier.move(report, report.parent / "Reports")

    assert tidier.last_change() is None


def test_rename_keeps_extension_when_none_given(tidier: FileTidier, report: Path) -> None:
    assert tidier.rename(report, "Q3 report").destination.name == "Q3 report.pdf"


def test_rename_uses_new_extension_when_given(tidier: FileTidier, report: Path) -> None:
    assert tidier.rename(report, "notes.txt").destination.name == "notes.txt"


def test_rename_folder_adds_no_extension(tidier: FileTidier, tmp_path: Path) -> None:
    folder = tmp_path / "Old"
    folder.mkdir()

    assert tidier.rename(folder, "New").destination == tmp_path / "New"


def test_rename_to_same_name_is_refused(tidier: FileTidier, report: Path) -> None:
    with pytest.raises(ToolError, match="already has"):
        tidier.rename(report, "report")


def test_undo_last_puts_file_back(tidier: FileTidier, report: Path) -> None:
    tidier.move(report, report.parent / "Reports")

    tidier.undo_last()

    assert report.exists()
    assert tidier.last_change() is None


def test_undo_last_goes_back_one_change_at_a_time(tidier: FileTidier, report: Path) -> None:
    moved = tidier.move(report, report.parent / "Reports").destination
    tidier.rename(moved, "final")

    tidier.undo_last()

    last = tidier.last_change()
    assert moved.exists()
    assert last is not None and last.destination == moved


def test_undo_last_survives_a_restart(tidier: FileTidier, report: Path, log_path: Path) -> None:
    tidier.move(report, report.parent / "Reports")

    FileTidier(log_path).undo_last()

    assert report.exists()


def test_undo_last_refuses_to_overwrite(tidier: FileTidier, report: Path) -> None:
    tidier.move(report, report.parent / "Reports")
    report.write_text("new file", encoding="utf-8")

    with pytest.raises(ToolError, match="something new"):
        tidier.undo_last()

    assert report.read_text(encoding="utf-8") == "new file"


def test_undo_last_when_file_is_gone(tidier: FileTidier, report: Path) -> None:
    tidier.move(report, report.parent / "Reports").destination.unlink()

    with pytest.raises(ToolError, match="isn't there"):
        tidier.undo_last()


def test_undo_last_with_nothing_to_undo(tidier: FileTidier) -> None:
    with pytest.raises(ToolError, match="no file change"):
        tidier.undo_last()


@pytest.mark.parametrize(("raw", "expected"), [("a/b:c?.txt", "abc.txt"), ("  plan.  ", "plan")])
def test_clean_name_removes_forbidden_characters(raw: str, expected: str) -> None:
    assert clean_name(raw) == expected


def test_clean_name_empty_is_refused() -> None:
    with pytest.raises(ToolError):
        clean_name('<>:"')


def test_free_path_counts_up(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("", encoding="utf-8")
    (tmp_path / "a (2).txt").write_text("", encoding="utf-8")

    assert free_path(tmp_path / "a.txt").name == "a (3).txt"


def test_move_folder_into_itself_creates_nothing(tidier: FileTidier, tmp_path: Path) -> None:
    folder = tmp_path / "Photos"
    folder.mkdir()

    with pytest.raises(ToolError, match="into itself"):
        tidier.move(folder, folder / "Inner")

    assert not (folder / "Inner").exists()


def test_move_refuses_when_a_file_appears_at_the_target(
    tidier: FileTidier, report: Path, mocker: MockerFixture
) -> None:
    mocker.patch("core.file_tidy.os.rename", side_effect=FileExistsError)

    with pytest.raises(ToolError, match="appeared"):
        tidier.move(report, report.parent / "Reports")

    assert report.exists()


def test_move_across_drives_falls_back_to_copying(tidier: FileTidier, report: Path, mocker: MockerFixture) -> None:
    other_drive = OSError("different drive")
    other_drive.winerror = 17
    mocker.patch("core.file_tidy.os.rename", side_effect=other_drive)

    change = tidier.move(report, report.parent / "Reports")

    assert change.destination.read_text(encoding="utf-8") == "report"


def test_undo_is_put_back_when_the_log_cannot_be_saved(tidier: FileTidier, report: Path, mocker: MockerFixture) -> None:
    moved = tidier.move(report, report.parent / "Reports")
    mocker.patch.object(FileTidier, "_rewrite_log", side_effect=OSError("disk full"))

    with pytest.raises(ToolError, match="undo log"):
        tidier.undo_last()

    assert moved.destination.exists() and not report.exists()
    assert tidier.last_change() == moved


def test_move_is_put_back_when_the_log_cannot_be_saved(tidier: FileTidier, report: Path, mocker: MockerFixture) -> None:
    mocker.patch.object(FileTidier, "_append", side_effect=OSError("disk full"))

    with pytest.raises(ToolError, match="Nothing was moved"):
        tidier.move(report, report.parent / "Reports")

    assert report.exists()


def test_damaged_log_lines_are_skipped(tidier: FileTidier, report: Path, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True)
    log_path.write_text('{broken\n{"to": "missing from"}\n', encoding="utf-8")

    moved = tidier.move(report, report.parent / "Reports")

    last = tidier.last_change()
    assert last is not None and last.destination == moved.destination
    tidier.undo_last()
    assert report.exists()


def test_rename_changes_only_the_case(tidier: FileTidier, report: Path) -> None:
    change = tidier.rename(report, "Report")

    assert change.destination.name == "Report.pdf"
    assert [p.name for p in report.parent.iterdir()] == ["Report.pdf"]
    tidier.undo_last()
    assert [p.name for p in report.parent.iterdir()] == ["report.pdf"]
