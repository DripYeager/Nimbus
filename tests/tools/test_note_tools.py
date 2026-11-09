from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from core.exceptions import ToolError
from tools.note_tools import list_notes, save_note, search_notes


@pytest.fixture
def notes(tmp_path: Path, mocker: MockerFixture) -> Path:
    folder = tmp_path / "notes"
    mocker.patch("tools.note_tools.notes_dir", return_value=folder)
    return folder


def _write_note(folder: Path, name: str, text: str, mtime: float) -> Path:
    folder.mkdir(exist_ok=True)
    path = folder / name
    path.write_text(text, encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def test_save_note_writes_markdown_with_heading(notes: Path) -> None:
    path = save_note("Groceries", "milk, eggs")
    assert path.parent == notes
    assert path.read_text(encoding="utf-8") == "# Groceries\n\nmilk, eggs\n"


def test_save_note_names_file_with_timestamp_and_slug(notes: Path) -> None:
    path = save_note("Call Bob @ 5pm!", "")
    assert path.name.endswith("_call-bob-5pm.md")
    assert path.name[:17].replace("-", "").replace("_", "").isdigit()


def test_save_note_truncates_long_slug(notes: Path) -> None:
    path = save_note("word " * 30, "body")
    slug = path.stem.split("_", 2)[2]
    assert len(slug) <= 40
    assert not slug.endswith("-")


def test_save_note_uses_default_slug_for_symbol_only_title(notes: Path) -> None:
    assert save_note("!!!", "body").name.endswith("_note.md")


def test_save_note_derives_title_from_body(notes: Path) -> None:
    path = save_note("", "Book dentist\nsometime next week")
    assert path.read_text(encoding="utf-8").startswith("# Book dentist\n\n")


def test_save_note_does_not_overwrite_same_second_note(notes: Path, mocker: MockerFixture) -> None:
    clock = mocker.patch("tools.note_tools.datetime")
    clock.now.return_value = datetime(2026, 11, 10, 9, 30, 0)
    first = save_note("Same", "one")
    second = save_note("Same", "two")
    assert first.name == "2026-11-10_093000_same.md"
    assert second.name == "2026-11-10_093000_same-2.md"


def test_save_note_raises_when_title_and_body_empty(notes: Path) -> None:
    with pytest.raises(ToolError, match="empty note"):
        save_note("  ", "\n")
    assert not notes.exists()


def test_save_note_raises_when_folder_not_writable(notes: Path, mocker: MockerFixture) -> None:
    mocker.patch.object(Path, "write_text", side_effect=PermissionError("denied"))
    with pytest.raises(ToolError, match="writable"):
        save_note("Title", "body")


def test_list_notes_returns_newest_first(notes: Path) -> None:
    _write_note(notes, "a.md", "# Older\n\nfirst", mtime=1_000)
    _write_note(notes, "b.md", "# Newer\n\nsecond", mtime=2_000)
    assert [note.title for note in list_notes()] == ["Newer", "Older"]


def test_list_notes_applies_limit(notes: Path) -> None:
    for index in range(3):
        _write_note(notes, f"{index}.md", f"# Note {index}\n\nbody", mtime=1_000 + index)
    assert [note.title for note in list_notes(limit=2)] == ["Note 2", "Note 1"]


def test_list_notes_returns_empty_when_folder_missing(notes: Path) -> None:
    assert list_notes() == []


def test_list_notes_uses_filename_when_heading_missing(notes: Path) -> None:
    _write_note(notes, "plain.md", "just text", mtime=1_000)
    note = list_notes()[0]
    assert (note.title, note.preview) == ("plain", "just text")


def test_list_notes_truncates_preview(notes: Path) -> None:
    _write_note(notes, "long.md", "# Long\n\n" + "x" * 500, mtime=1_000)
    assert len(list_notes()[0].preview) == 200


def test_list_notes_raises_for_zero_limit(notes: Path) -> None:
    with pytest.raises(ToolError, match="limit"):
        list_notes(limit=0)


def test_search_notes_matches_body_case_insensitively(notes: Path) -> None:
    _write_note(notes, "a.md", "# Groceries\n\nMilk and EGGS", mtime=1_000)
    _write_note(notes, "b.md", "# Ideas\n\nnew app", mtime=2_000)
    assert [note.title for note in search_notes("eggs")] == ["Groceries"]


def test_search_notes_matches_title(notes: Path) -> None:
    _write_note(notes, "a.md", "# Trip to Lisbon\n\npack light", mtime=1_000)
    assert [note.title for note in search_notes("lisbon")] == ["Trip to Lisbon"]


def test_search_notes_requires_every_word(notes: Path) -> None:
    _write_note(notes, "a.md", "# Groceries\n\nmilk", mtime=1_000)
    assert search_notes("milk bread") == []


def test_search_notes_orders_matches_newest_first(notes: Path) -> None:
    _write_note(notes, "a.md", "# Old todo\n\nx", mtime=1_000)
    _write_note(notes, "b.md", "# New todo\n\ny", mtime=2_000)
    assert [note.title for note in search_notes("todo")] == ["New todo", "Old todo"]


def test_search_notes_blank_query_returns_recent_notes(notes: Path) -> None:
    _write_note(notes, "a.md", "# One\n\nx", mtime=1_000)
    _write_note(notes, "b.md", "# Two\n\ny", mtime=2_000)
    assert [note.title for note in search_notes("  ", limit=1)] == ["Two"]


def test_search_notes_skips_unreadable_note(notes: Path) -> None:
    _write_note(notes, "good.md", "# Good\n\nmeeting", mtime=1_000)
    (notes / "bad.md").write_bytes(b"\xff\xfe\xfa meeting")
    assert [note.title for note in search_notes("meeting")] == ["Good"]


def test_search_notes_raises_for_negative_limit(notes: Path) -> None:
    with pytest.raises(ToolError, match="limit"):
        search_notes("x", limit=-1)
