from __future__ import annotations

from pathlib import Path

import pytest

from config.settings import Settings
from core.index_rules import BYTES_PER_MB, IndexRules
from models.schema import FileCategory, IndexSource


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "Documents"


def _rules(*sources: IndexSource, exclude: tuple[str, ...] = (), max_bytes: int = 1000) -> IndexRules:
    return IndexRules(
        sources=sources,
        content_extensions=frozenset({".txt", ".pdf"}),
        max_file_bytes=max_bytes,
        exclude_patterns=exclude,
    )


def test_from_settings_reads_contents_only_for_the_chosen_categories() -> None:
    rules = IndexRules.from_settings(Settings(_env_file=None, sources=[], file_categories=[FileCategory.PDFS]))

    assert rules.content_extensions == frozenset({".pdf"})


def test_from_settings_converts_the_size_cap_and_lowercases_patterns() -> None:
    rules = IndexRules.from_settings(
        Settings(_env_file=None, sources=[], max_file_size_mb=2, exclude_patterns=["*.BAK"])
    )

    assert rules.max_file_bytes == 2 * BYTES_PER_MB
    assert rules.exclude_patterns == ("*.bak",)


@pytest.mark.parametrize("name", ["node_modules", ".git", "Node_Modules", "__pycache__", "AppData"])
def test_is_excluded_dir_skips_well_known_noise_folders(root: Path, name: str) -> None:
    assert _rules(IndexSource(path=root)).is_excluded_dir(root / name) is True


def test_is_excluded_dir_honours_a_user_glob(root: Path) -> None:
    assert _rules(IndexSource(path=root), exclude=("build*",)).is_excluded_dir(root / "build-output") is True


def test_is_excluded_dir_keeps_an_ordinary_folder(root: Path) -> None:
    assert _rules(IndexSource(path=root)).is_excluded_dir(root / "Invoices") is False


@pytest.mark.parametrize("name", ["~$report.docx", "setup.tmp", "movie.mp4.crdownload", "desktop.ini", "Thumbs.db"])
def test_is_excluded_file_skips_temp_and_system_files(root: Path, name: str) -> None:
    assert _rules(IndexSource(path=root)).is_excluded_file(root / name) is True


def test_is_excluded_file_honours_a_user_glob(root: Path) -> None:
    assert _rules(IndexSource(path=root), exclude=("*.bak",)).is_excluded_file(root / "old.bak") is True


def test_is_excluded_file_skips_a_file_inside_an_excluded_subfolder(root: Path) -> None:
    rules = _rules(IndexSource(path=root))

    assert rules.is_excluded_file(root / "app" / "node_modules" / "lib" / "index.txt") is True


def test_is_excluded_file_keeps_a_file_in_a_source_picked_inside_appdata(tmp_path: Path) -> None:
    source = tmp_path / "AppData" / "Roaming" / "Notes"

    assert _rules(IndexSource(path=source)).is_excluded_file(source / "todo.txt") is False


def test_is_excluded_file_keeps_an_ordinary_file(root: Path) -> None:
    assert _rules(IndexSource(path=root)).is_excluded_file(root / "Taxes" / "2025.pdf") is False


def test_should_read_contents_is_true_for_a_supported_file_in_a_content_source(root: Path) -> None:
    assert _rules(IndexSource(path=root)).should_read_contents(root / "a.txt", 10) is True


def test_should_read_contents_is_false_in_a_names_only_source(root: Path) -> None:
    rules = _rules(IndexSource(path=root, include_contents=False))

    assert rules.should_read_contents(root / "a.txt", 10) is False


def test_should_read_contents_is_false_for_an_unsupported_extension(root: Path) -> None:
    assert _rules(IndexSource(path=root)).should_read_contents(root / "photo.jpg", 10) is False


def test_should_read_contents_matches_the_extension_case_insensitively(root: Path) -> None:
    assert _rules(IndexSource(path=root)).should_read_contents(root / "SCAN.PDF", 10) is True


@pytest.mark.parametrize("size", [0, 1001])
def test_should_read_contents_is_false_for_an_empty_or_oversized_file(root: Path, size: int) -> None:
    assert _rules(IndexSource(path=root), max_bytes=1000).should_read_contents(root / "a.txt", size) is False


def test_should_read_contents_is_false_outside_every_source(root: Path, tmp_path: Path) -> None:
    assert _rules(IndexSource(path=root)).should_read_contents(tmp_path / "elsewhere.txt", 10) is False


def test_source_for_picks_the_most_specific_source(root: Path) -> None:
    inner = IndexSource(path=root / "Private", include_contents=False)
    rules = _rules(IndexSource(path=root), inner)

    assert rules.source_for(root / "Private" / "diary.txt") == inner


def test_source_for_ignores_case(root: Path) -> None:
    source = IndexSource(path=root)

    assert _rules(source).source_for(Path(str(root).upper()) / "a.txt") == source


def test_source_for_does_not_match_a_sibling_with_the_same_prefix(root: Path) -> None:
    rules = _rules(IndexSource(path=root))

    assert rules.source_for(root.with_name("Documents2") / "a.txt") is None


def test_is_covered_is_true_for_an_included_file(root: Path) -> None:
    assert _rules(IndexSource(path=root)).is_covered(root / "a.txt") is True


def test_is_covered_is_false_for_an_excluded_file(root: Path) -> None:
    assert _rules(IndexSource(path=root)).is_covered(root / ".git" / "config.txt") is False


def test_is_covered_is_false_outside_every_source(root: Path, tmp_path: Path) -> None:
    assert _rules(IndexSource(path=root)).is_covered(tmp_path / "a.txt") is False
