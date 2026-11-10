from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from core.file_catalog import FileCatalog
from core.index_service import IndexService
from core.vector_store import VectorStore
from models.schema import CatalogEntry, CatalogStatus, IndexSource
from tests.core.index_service_helpers import (
    MODEL,
    ServiceFactory,
    catalog_statuses,
    drain_queue,
    start_and_index,
    wait_until,
    write_file,
)


def test_rescan_catalogs_content_and_name_only_files(service: IndexService, docs: Path, catalog: FileCatalog) -> None:
    write_file(docs / "notes.txt")
    write_file(docs / "song.mp3")

    service.rescan()

    assert catalog_statuses(catalog) == {"notes.txt": CatalogStatus.PENDING, "song.mp3": CatalogStatus.NAME_ONLY}


def test_rescan_queues_only_content_files(service: IndexService, docs: Path) -> None:
    notes = write_file(docs / "notes.txt")
    write_file(docs / "song.mp3")

    service.rescan()

    assert drain_queue(service) == [notes]


def test_rescan_never_catalogs_files_in_excluded_folders(
    service: IndexService, docs: Path, catalog: FileCatalog
) -> None:
    write_file(docs / "app" / "node_modules" / "lib" / "readme.txt")
    write_file(docs / "repo" / ".git" / "HEAD")
    write_file(docs / "keep.txt")

    service.rescan()

    assert list(catalog_statuses(catalog)) == ["keep.txt"]


def test_rescan_honours_user_exclude_globs(
    configure: Callable[..., None], make_service: ServiceFactory, docs: Path, catalog: FileCatalog
) -> None:
    configure(IndexSource(path=docs), exclude=["*.bak", "drafts"])
    write_file(docs / "old.bak")
    write_file(docs / "drafts" / "idea.txt")
    write_file(docs / "final.txt")

    make_service().rescan()

    assert list(catalog_statuses(catalog)) == ["final.txt"]


def test_rescan_indexes_a_source_folder_picked_inside_appdata(
    configure: Callable[..., None], make_service: ServiceFactory, tmp_path: Path, catalog: FileCatalog
) -> None:
    notes = tmp_path / "AppData" / "Roaming" / "Notes"
    write_file(notes / "todo.txt")
    configure(IndexSource(path=notes))

    make_service().rescan()

    assert catalog_statuses(catalog) == {"todo.txt": CatalogStatus.PENDING}


def test_rescan_never_queues_content_from_a_names_only_source(
    configure: Callable[..., None], make_service: ServiceFactory, docs: Path, catalog: FileCatalog
) -> None:
    configure(IndexSource(path=docs, include_contents=False))
    write_file(docs / "secret.txt")
    service = make_service()

    service.rescan()

    assert catalog_statuses(catalog) == {"secret.txt": CatalogStatus.NAME_ONLY}
    assert drain_queue(service) == []


def test_start_indexes_every_content_file(service: IndexService, docs: Path, store: VectorStore) -> None:
    notes = write_file(docs / "notes.txt")

    start_and_index(service, expected_indexed=1)

    assert store.content_hash_for(str(notes)) is not None


def test_rescan_skips_unchanged_files_without_reading_them(
    service: IndexService, docs: Path, mocker: MockerFixture
) -> None:
    write_file(docs / "notes.txt")
    start_and_index(service, expected_indexed=1)
    service.stop()
    opener = mocker.patch("pathlib.Path.open", side_effect=AssertionError("a file was read"))

    service.rescan()

    assert drain_queue(service) == []
    opener.assert_not_called()


def test_rescan_requeues_a_file_whose_size_changed(service: IndexService, docs: Path) -> None:
    notes = write_file(docs / "notes.txt")
    start_and_index(service, expected_indexed=1)
    service.stop()
    write_file(notes, "quarterly numbers look good, revised")

    service.rescan()

    assert drain_queue(service) == [notes]


def test_apply_settings_drops_vector_rows_when_a_source_becomes_names_only(
    service: IndexService, configure: Callable[..., None], docs: Path, store: VectorStore, catalog: FileCatalog
) -> None:
    notes = write_file(docs / "notes.txt")
    start_and_index(service, expected_indexed=1)

    configure(IndexSource(path=docs, include_contents=False))
    service.apply_settings()

    assert store.content_hash_for(str(notes)) is None
    assert catalog_statuses(catalog) == {"notes.txt": CatalogStatus.NAME_ONLY}


def test_apply_settings_unqueues_a_waiting_file_when_its_source_becomes_names_only(
    service: IndexService, configure: Callable[..., None], docs: Path
) -> None:
    write_file(docs / "notes.txt")
    service.rescan()

    configure(IndexSource(path=docs, include_contents=False))
    service.apply_settings()

    assert drain_queue(service) == []


def test_rescan_forgets_a_deleted_file_in_the_catalog_and_store(
    service: IndexService, docs: Path, store: VectorStore, catalog: FileCatalog
) -> None:
    notes = write_file(docs / "notes.txt")
    start_and_index(service, expected_indexed=1)
    service.stop()
    notes.unlink()

    service.rescan()

    assert catalog.snapshot() == {}
    assert store.content_hash_for(str(notes)) is None


def test_rescan_unqueues_a_file_deleted_before_it_was_indexed(service: IndexService, docs: Path) -> None:
    notes = write_file(docs / "notes.txt")
    service.rescan()
    notes.unlink()

    service.rescan()

    assert drain_queue(service) == []


def test_rescan_keeps_files_under_a_source_that_is_temporarily_missing(
    configure: Callable[..., None], make_service: ServiceFactory, docs: Path, tmp_path: Path, catalog: FileCatalog
) -> None:
    usb = tmp_path / "USB"
    write_file(usb / "holiday.jpg")
    configure(IndexSource(path=docs), IndexSource(path=usb))
    service = make_service()
    service.rescan()
    usb.rename(tmp_path / "unplugged")

    service.rescan()

    assert list(catalog_statuses(catalog)) == ["holiday.jpg"]


def test_rescan_logs_a_scan_failure_and_clears_is_scanning(
    service: IndexService, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    mocker.patch("core.index_service.scan_source", side_effect=RuntimeError("disk vanished"))

    with caplog.at_level(logging.ERROR):
        service.rescan()

    assert service.status().is_scanning is False
    assert any(record.levelno == logging.ERROR for record in caplog.records)


def test_status_counts_files_by_catalog_status(service: IndexService, docs: Path, catalog: FileCatalog) -> None:
    statuses = [CatalogStatus.INDEXED, CatalogStatus.PENDING, CatalogStatus.PENDING]
    statuses += [CatalogStatus.FAILED, CatalogStatus.NAME_ONLY]
    catalog.upsert(CatalogEntry(docs / f"{i}.txt", 1, 1.0, s) for i, s in enumerate(statuses))

    status = service.status()

    assert (status.cataloged_files, status.content_files) == (5, 4)
    assert (status.indexed_files, status.pending_files, status.failed_files) == (1, 2, 1)


def test_status_is_empty_for_a_fresh_install(service: IndexService) -> None:
    status = service.status()

    assert (status.cataloged_files, status.is_busy, status.progress_ratio) == (0, False, 1.0)


def test_set_paused_is_reflected_in_status(service: IndexService) -> None:
    service.start(MODEL)

    service.set_paused(True)

    assert service.status().is_paused is True


def test_set_paused_false_resumes_indexing(service: IndexService, docs: Path) -> None:
    service.start(MODEL)
    service.set_paused(True)
    write_file(docs / "notes.txt")
    service.rescan()

    service.set_paused(False)

    assert wait_until(lambda: service.status().indexed_files == 1)


def test_rescan_drops_rows_of_a_vanished_file_that_was_waiting_for_reindex(
    service: IndexService, docs: Path, store: VectorStore, catalog: FileCatalog
) -> None:
    notes = write_file(docs / "notes.txt")
    start_and_index(service, expected_indexed=1)
    service.stop()
    catalog.set_status(notes, CatalogStatus.PENDING)
    notes.unlink()

    service.rescan()

    assert store.content_hash_for(str(notes)) is None


def test_source_summaries_flag_the_folder_being_indexed(
    service: IndexService, docs: Path, catalog: FileCatalog, mocker: MockerFixture
) -> None:
    report = write_file(docs / "report.txt")
    catalog.upsert([CatalogEntry(report, 1, 1.0, CatalogStatus.PENDING)])
    mocker.patch.object(type(service._worker), "current_path", new_callable=mocker.PropertyMock, return_value=report)

    (summary,) = service.source_summaries()

    assert (summary.is_active, summary.current_file, summary.pending_count) == (True, "report.txt", 1)


def test_status_reports_the_full_path_being_indexed(service: IndexService, docs: Path, mocker: MockerFixture) -> None:
    report = docs / "report.txt"
    mocker.patch.object(type(service._worker), "current_path", new_callable=mocker.PropertyMock, return_value=report)

    assert service.status().current_path == str(report)
