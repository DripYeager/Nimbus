from __future__ import annotations

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

import core.directory_scanner as scanner_module
from core.directory_scanner import _stat_entry, scan_source
from core.index_rules import IndexRules
from models.schema import IndexSource


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "Documents"
    folder.mkdir()
    return folder


def _rules(root: Path, exclude: tuple[str, ...] = ()) -> IndexRules:
    return IndexRules(
        sources=(IndexSource(path=root),),
        content_extensions=frozenset({".txt"}),
        max_file_bytes=1000,
        exclude_patterns=exclude,
    )


def _write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_scan_source_yields_every_file_in_the_tree(root: Path) -> None:
    expected = {_write(root / "a.txt"), _write(root / "Taxes" / "2025" / "b.pdf")}

    assert {f.path for f in scan_source(root, _rules(root))} == expected


def test_scan_source_reports_size_and_mtime(root: Path) -> None:
    path = _write(root / "a.txt", "hello")

    [scanned] = scan_source(root, _rules(root))

    assert (scanned.size_bytes, scanned.modified_ts) == (5, path.stat().st_mtime)


def test_scan_source_never_lists_an_excluded_folder(root: Path, mocker: MockerFixture) -> None:
    _write(root / "app" / "node_modules" / "pkg" / "index.txt")
    _write(root / "app" / "main.txt")
    lister = mocker.spy(scanner_module, "_list_directory")

    files = list(scan_source(root, _rules(root)))

    assert [f.path.name for f in files] == ["main.txt"]
    assert all("node_modules" not in str(call.args[0]) for call in lister.call_args_list)


def test_scan_source_prunes_a_folder_matching_a_user_glob(root: Path) -> None:
    _write(root / "build-2024" / "out.txt")
    _write(root / "keep.txt")

    assert [f.path.name for f in scan_source(root, _rules(root, exclude=("build-*",)))] == ["keep.txt"]


def test_scan_source_skips_office_lock_files(root: Path) -> None:
    _write(root / "~$report.docx")
    _write(root / "report.docx")

    assert [f.path.name for f in scan_source(root, _rules(root))] == ["report.docx"]


def test_scan_source_yields_nothing_for_a_missing_root(tmp_path: Path) -> None:
    missing = tmp_path / "unplugged"

    assert list(scan_source(missing, _rules(missing))) == []


def test_stat_entry_returns_none_for_a_file_that_vanished_mid_scan(mocker: MockerFixture) -> None:
    entry = mocker.Mock()
    entry.stat.side_effect = FileNotFoundError("gone")

    assert _stat_entry(entry) is None
