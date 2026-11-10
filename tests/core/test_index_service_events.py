from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from unittest.mock import Mock

from core.file_catalog import FileCatalog, path_key
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


def test_apply_settings_purges_a_removed_source_folder(
    configure: Callable[..., None],
    make_service: ServiceFactory,
    docs: Path,
    tmp_path: Path,
    store: VectorStore,
    catalog: FileCatalog,
) -> None:
    old = write_file(tmp_path / "Old" / "report.txt")
    write_file(docs / "keep.txt")
    configure(IndexSource(path=docs), IndexSource(path=tmp_path / "Old"))
    service = make_service()
    start_and_index(service, expected_indexed=2)

    configure(IndexSource(path=docs))
    service.apply_settings()

    assert list(catalog_statuses(catalog)) == ["keep.txt"]
    assert store.content_hash_for(str(old)) is None


def test_path_removed_on_a_folder_purges_everything_under_it(
    service: IndexService, docs: Path, store: VectorStore, catalog: FileCatalog
) -> None:
    inner = write_file(docs / "Project" / "plan.txt")
    write_file(docs / "Project2" / "keep.txt")
    start_and_index(service, expected_indexed=2)

    service.path_removed(docs / "Project")

    assert list(catalog_statuses(catalog)) == ["keep.txt"]
    assert store.content_hash_for(str(inner)) is None


def test_path_removed_forgets_a_single_file(
    service: IndexService, docs: Path, store: VectorStore, catalog: FileCatalog
) -> None:
    notes = write_file(docs / "notes.txt")
    start_and_index(service, expected_indexed=1)

    service.path_removed(notes)

    assert catalog.snapshot() == {}
    assert store.content_hash_for(str(notes)) is None


def test_path_changed_queues_a_saved_file_ahead_of_the_backlog(service: IndexService, docs: Path) -> None:
    backlog = write_file(docs / "backlog.txt")
    service.rescan()
    saved = write_file(docs / "just-saved.txt")

    service.path_changed(saved)

    assert drain_queue(service) == [saved, backlog]


def test_path_changed_catalogs_a_names_only_file_without_queueing_it(
    service: IndexService, docs: Path, catalog: FileCatalog
) -> None:
    photo = write_file(docs / "photo.jpg")

    service.path_changed(photo)

    assert catalog_statuses(catalog) == {"photo.jpg": CatalogStatus.NAME_ONLY}
    assert drain_queue(service) == []


def test_path_changed_ignores_a_file_in_an_excluded_folder(
    service: IndexService, docs: Path, catalog: FileCatalog
) -> None:
    service.path_changed(write_file(docs / "node_modules" / "index.txt"))

    assert catalog.snapshot() == {}


def test_path_changed_ignores_a_file_outside_every_source(
    service: IndexService, tmp_path: Path, catalog: FileCatalog
) -> None:
    service.path_changed(write_file(tmp_path / "Elsewhere" / "a.txt"))

    assert catalog.snapshot() == {}


def test_path_changed_ignores_a_path_that_no_longer_exists(
    service: IndexService, docs: Path, catalog: FileCatalog
) -> None:
    service.path_changed(docs / "gone.txt")

    assert catalog.snapshot() == {}


def test_path_changed_scans_a_whole_folder_moved_into_a_source(
    service: IndexService, docs: Path, catalog: FileCatalog
) -> None:
    write_file(docs / "Imported" / "a.txt")
    write_file(docs / "Imported" / "deep" / "b.jpg")

    service.path_changed(docs / "Imported")

    assert catalog_statuses(catalog) == {"a.txt": CatalogStatus.PENDING, "b.jpg": CatalogStatus.NAME_ONLY}


def test_source_summaries_reports_counts_per_source(
    configure: Callable[..., None], make_service: ServiceFactory, docs: Path, tmp_path: Path
) -> None:
    write_file(docs / "a.txt")
    write_file(docs / "b.jpg")
    configure(IndexSource(path=docs), IndexSource(path=tmp_path / "Missing", include_contents=False))
    service = make_service()
    start_and_index(service, expected_indexed=1)

    summaries = service.source_summaries()

    assert [(s.exists, s.file_count, s.indexed_count) for s in summaries] == [(True, 2, 1), (False, 0, 0)]


def test_rebuild_requeues_every_indexed_file(service: IndexService, docs: Path, catalog: FileCatalog) -> None:
    catalog.upsert([CatalogEntry(write_file(docs / "a.txt"), 1, 1.0, CatalogStatus.INDEXED)])

    service.rebuild()

    assert catalog.snapshot()[path_key(docs / "a.txt")].status is CatalogStatus.PENDING


def test_start_reindexes_everything_after_an_embedding_model_change(
    service: IndexService, docs: Path, store: VectorStore, embedder: Mock
) -> None:
    write_file(docs / "notes.txt")
    start_and_index(service, expected_indexed=1)
    service.stop()
    embedder.embed.reset_mock()
    store.ensure_compatible("an/older-model")

    service.start(MODEL)

    assert wait_until(lambda: embedder.embed.called)


def test_rebuild_drops_stored_chunks_so_every_file_is_really_reread(
    service: IndexService, docs: Path, store: VectorStore
) -> None:
    notes = write_file(docs / "notes.txt")
    start_and_index(service, expected_indexed=1)
    service.stop()

    service.rebuild()

    assert store.content_hash_for(str(notes)) is None


def test_path_changed_skips_a_new_excluded_folder_without_walking_it(
    service: IndexService, docs: Path, catalog: FileCatalog
) -> None:
    write_file(docs / "node_modules" / "pkg" / "index.js")

    service.path_changed(docs / "node_modules")

    assert catalog.snapshot() == {}
