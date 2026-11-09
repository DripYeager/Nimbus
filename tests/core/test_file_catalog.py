from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from core.exceptions import IndexingError
from core.file_catalog import FileCatalog, folder_prefix, path_key
from models.schema import CatalogEntry, CatalogStatus

DOCS = Path("C:/Users/me/Docs")


@pytest.fixture
def catalog(tmp_path: Path) -> Iterator[FileCatalog]:
    opened = FileCatalog(tmp_path / "catalog.db")
    opened.connect()
    yield opened
    opened.close()


def _entry(path: Path, status: CatalogStatus = CatalogStatus.PENDING, modified_ts: float = 1000.0) -> CatalogEntry:
    return CatalogEntry(path=path, size_bytes=10, modified_ts=modified_ts, status=status)


def _stored_error(db_path: Path, path: Path) -> str | None:
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute("SELECT error FROM files WHERE path_key = ?", (path_key(path),)).fetchone()[0]


def test_path_key_lowercases_the_path() -> None:
    assert path_key("C:\\Docs\\Report.PDF") == "c:\\docs\\report.pdf"


def test_folder_prefix_ends_with_exactly_one_separator() -> None:
    assert folder_prefix("C:\\Docs\\") == "c:\\docs\\"


def test_connect_raises_indexing_error_when_the_folder_is_a_file(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")

    with pytest.raises(IndexingError):
        FileCatalog(blocker / "catalog.db").connect()


def test_snapshot_raises_indexing_error_before_connect(tmp_path: Path) -> None:
    with pytest.raises(IndexingError, match="connect"):
        FileCatalog(tmp_path / "catalog.db").snapshot()


def test_upsert_then_snapshot_round_trips_entries_by_lowercased_key(catalog: FileCatalog) -> None:
    entry = _entry(DOCS / "Report.pdf")
    catalog.upsert([entry])

    assert catalog.snapshot() == {path_key(entry.path): entry}


def test_upsert_replaces_an_existing_row_and_clears_its_error(catalog: FileCatalog, tmp_path: Path) -> None:
    path = DOCS / "a.txt"
    catalog.upsert([_entry(path)])
    catalog.set_status(path, CatalogStatus.FAILED, error="parser crashed")

    catalog.upsert([_entry(path, modified_ts=2000.0)])

    assert catalog.snapshot()[path_key(path)].status is CatalogStatus.PENDING
    assert _stored_error(tmp_path / "catalog.db", path) is None


def test_set_status_records_the_status_and_error(catalog: FileCatalog, tmp_path: Path) -> None:
    path = DOCS / "a.txt"
    catalog.upsert([_entry(path)])

    catalog.set_status(path, CatalogStatus.FAILED, error="encrypted")

    assert catalog.snapshot()[path_key(path)].status is CatalogStatus.FAILED
    assert _stored_error(tmp_path / "catalog.db", path) == "encrypted"


def test_remove_deletes_only_the_given_paths(catalog: FileCatalog) -> None:
    catalog.upsert([_entry(DOCS / "a.txt"), _entry(DOCS / "b.txt")])

    catalog.remove([DOCS / "A.TXT"])

    assert list(catalog.snapshot()) == [path_key(DOCS / "b.txt")]


def test_remove_under_spares_a_sibling_folder_with_the_same_prefix(catalog: FileCatalog) -> None:
    sibling = Path("C:/Users/me/Docs2/keep.txt")
    catalog.upsert([_entry(DOCS / "a.txt"), _entry(DOCS / "sub" / "b.txt"), _entry(sibling)])

    catalog.remove_under(Path("C:/USERS/me/docs"))

    assert list(catalog.snapshot()) == [path_key(sibling)]


def test_requeue_all_resets_indexed_and_failed_but_not_name_only(catalog: FileCatalog) -> None:
    catalog.upsert(
        [
            _entry(DOCS / "done.txt", CatalogStatus.INDEXED),
            _entry(DOCS / "broken.txt", CatalogStatus.FAILED),
            _entry(DOCS / "photo.jpg", CatalogStatus.NAME_ONLY),
        ]
    )

    catalog.requeue_all()

    assert catalog.status_counts() == {CatalogStatus.PENDING: 2, CatalogStatus.NAME_ONLY: 1}


def test_pending_files_lists_only_pending_files_with_their_mtime(catalog: FileCatalog) -> None:
    catalog.upsert([_entry(DOCS / "todo.txt", modified_ts=5.0), _entry(DOCS / "done.txt", CatalogStatus.INDEXED)])

    assert catalog.pending_files() == [(DOCS / "todo.txt", 5.0)]


def test_status_counts_is_empty_for_an_empty_catalog(catalog: FileCatalog) -> None:
    assert catalog.status_counts() == {}


def test_count_under_counts_all_and_indexed_files_below_a_folder(catalog: FileCatalog) -> None:
    catalog.upsert(
        [
            _entry(DOCS / "a.txt", CatalogStatus.INDEXED),
            _entry(DOCS / "b.jpg", CatalogStatus.NAME_ONLY),
            _entry(Path("C:/Users/me/Docs2/c.txt"), CatalogStatus.INDEXED),
        ]
    )

    assert catalog.count_under(DOCS) == (2, 1)


def test_count_under_is_zero_for_an_unknown_folder(catalog: FileCatalog) -> None:
    assert catalog.count_under(DOCS) == (0, 0)


def test_search_names_finds_a_file_by_a_loose_name(catalog: FileCatalog) -> None:
    catalog.upsert([_entry(DOCS / "Quarterly_Report_2025.xlsx"), _entry(DOCS / "holiday.jpg")])

    matches = catalog.search_names("quarterly report")

    assert matches[0].file_name == "Quarterly_Report_2025.xlsx"
    assert matches[0].file_path == str(DOCS / "Quarterly_Report_2025.xlsx")


def test_search_names_drops_weak_matches(catalog: FileCatalog) -> None:
    catalog.upsert([_entry(DOCS / "holiday.jpg")])

    assert catalog.search_names("tax return") == []


def test_search_names_returns_nothing_for_a_blank_query(catalog: FileCatalog) -> None:
    catalog.upsert([_entry(DOCS / "holiday.jpg")])

    assert catalog.search_names("   ") == []


def test_recent_files_returns_files_since_the_cutoff_newest_first(catalog: FileCatalog) -> None:
    old, mid, new = (datetime(2026, m, 1).timestamp() for m in (1, 6, 9))
    catalog.upsert(
        [_entry(DOCS / "old.txt", modified_ts=old), _entry(DOCS / "mid.txt", modified_ts=mid)]
        + [_entry(DOCS / "new.txt", modified_ts=new)]
    )

    recent = catalog.recent_files(since=datetime(2026, 5, 1))

    assert [m.file_name for m in recent] == ["new.txt", "mid.txt"]


def test_get_meta_returns_none_for_an_unknown_key(catalog: FileCatalog) -> None:
    assert catalog.get_meta("missing") is None


def test_set_meta_overwrites_a_previous_value(catalog: FileCatalog) -> None:
    catalog.set_meta("model", "a")
    catalog.set_meta("model", "b")

    assert catalog.get_meta("model") == "b"


def test_catalog_contents_survive_a_reconnect(tmp_path: Path) -> None:
    first = FileCatalog(tmp_path / "catalog.db")
    first.connect()
    first.upsert([_entry(DOCS / "a.txt")])
    first.close()

    second = FileCatalog(tmp_path / "catalog.db")
    second.connect()

    assert list(second.snapshot()) == [path_key(DOCS / "a.txt")]
    second.close()


def test_upsert_raises_indexing_error_after_close(catalog: FileCatalog) -> None:
    catalog.close()

    with pytest.raises(IndexingError):
        catalog.upsert([_entry(DOCS / "a.txt")])


def test_search_names_sees_a_file_added_after_an_earlier_search(catalog: FileCatalog, tmp_path: Path) -> None:
    catalog.upsert([_entry(tmp_path / "budget.xlsx")])
    assert [m.file_name for m in catalog.search_names("budget")] == ["budget.xlsx"]

    catalog.upsert([_entry(tmp_path / "resume.pdf")])

    assert [m.file_name for m in catalog.search_names("resume")] == ["resume.pdf"]


def test_search_names_reuses_its_name_list_while_only_statuses_change(
    catalog: FileCatalog, tmp_path: Path, mocker: MockerFixture
) -> None:
    catalog.upsert([_entry(tmp_path / "budget.xlsx")])
    catalog.search_names("budget")
    read = mocker.spy(catalog, "_query")

    catalog.set_status(tmp_path / "budget.xlsx", CatalogStatus.INDEXED)
    catalog.search_names("budget")

    assert read.call_count == 0


def test_search_names_forgets_a_removed_file(catalog: FileCatalog, tmp_path: Path) -> None:
    catalog.upsert([_entry(tmp_path / "budget.xlsx")])
    catalog.search_names("budget")

    catalog.remove([tmp_path / "budget.xlsx"])

    assert catalog.search_names("budget") == []
