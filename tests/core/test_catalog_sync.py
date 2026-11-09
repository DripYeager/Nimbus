from __future__ import annotations

from pathlib import Path

import pytest

from core.catalog_sync import find_vanished, plan_sync, target_status
from core.file_catalog import path_key
from core.index_rules import IndexRules
from models.schema import CatalogEntry, CatalogStatus, IndexSource, ScannedFile


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "Docs"
    folder.mkdir()
    return folder


def _rules(*sources: IndexSource) -> IndexRules:
    return IndexRules(sources=sources, content_extensions=frozenset({".txt"}), max_file_bytes=1000, exclude_patterns=())


def _scanned(path: Path, size: int = 10, mtime: float = 100.0) -> ScannedFile:
    return ScannedFile(path=path, size_bytes=size, modified_ts=mtime)


def _cataloged(path: Path, status: CatalogStatus, size: int = 10, mtime: float = 100.0) -> dict[str, CatalogEntry]:
    return {path_key(path): CatalogEntry(path, size, mtime, status)}


def test_plan_sync_queues_a_new_content_file(root: Path) -> None:
    path = root / "a.txt"

    plan = plan_sync([_scanned(path)], {}, _rules(IndexSource(path=root)), set())

    assert plan.upserts == [CatalogEntry(path, 10, 100.0, CatalogStatus.PENDING)]
    assert plan.to_queue == [(path, 100.0)]


def test_plan_sync_never_queues_a_file_in_a_names_only_source(root: Path) -> None:
    path = root / "a.txt"

    plan = plan_sync([_scanned(path)], {}, _rules(IndexSource(path=root, include_contents=False)), set())

    assert plan.upserts == [CatalogEntry(path, 10, 100.0, CatalogStatus.NAME_ONLY)]
    assert plan.to_queue == []


def test_plan_sync_catalogs_an_unsupported_type_by_name_only(root: Path) -> None:
    plan = plan_sync([_scanned(root / "photo.jpg")], {}, _rules(IndexSource(path=root)), set())

    assert [e.status for e in plan.upserts] == [CatalogStatus.NAME_ONLY]
    assert plan.to_queue == []


@pytest.mark.parametrize("status", [CatalogStatus.INDEXED, CatalogStatus.FAILED, CatalogStatus.NAME_ONLY])
def test_plan_sync_skips_a_settled_unchanged_file(root: Path, status: CatalogStatus) -> None:
    path = root / ("a.txt" if status is not CatalogStatus.NAME_ONLY else "a.jpg")

    plan = plan_sync([_scanned(path)], _cataloged(path, status), _rules(IndexSource(path=root)), set())

    assert (plan.upserts, plan.to_queue, plan.drop_content) == ([], [], [])


def test_plan_sync_requeues_an_unchanged_pending_file_without_rewriting_it(root: Path) -> None:
    path = root / "a.txt"

    plan = plan_sync([_scanned(path)], _cataloged(path, CatalogStatus.PENDING), _rules(IndexSource(path=root)), set())

    assert plan.upserts == []
    assert plan.to_queue == [(path, 100.0)]


@pytest.mark.parametrize(("size", "mtime"), [(11, 100.0), (10, 200.0)])
def test_plan_sync_reindexes_a_file_whose_size_or_mtime_changed(root: Path, size: int, mtime: float) -> None:
    path = root / "a.txt"
    snapshot = _cataloged(path, CatalogStatus.INDEXED)

    plan = plan_sync([_scanned(path, size, mtime)], snapshot, _rules(IndexSource(path=root)), set())

    assert [e.status for e in plan.upserts] == [CatalogStatus.PENDING]
    assert plan.to_queue == [(path, mtime)]


def test_plan_sync_drops_content_of_an_indexed_file_that_became_names_only(root: Path) -> None:
    path = root / "a.txt"
    snapshot = _cataloged(path, CatalogStatus.INDEXED)

    plan = plan_sync([_scanned(path)], snapshot, _rules(IndexSource(path=root, include_contents=False)), set())

    assert plan.drop_content == [path]
    assert [e.status for e in plan.upserts] == [CatalogStatus.NAME_ONLY]
    assert plan.to_queue == []


def test_plan_sync_drops_content_of_a_pending_file_that_became_names_only(root: Path) -> None:
    path = root / "a.txt"
    snapshot = _cataloged(path, CatalogStatus.PENDING)

    plan = plan_sync([_scanned(path)], snapshot, _rules(IndexSource(path=root, include_contents=False)), set())

    assert plan.drop_content == [path]


def test_plan_sync_records_every_scanned_key_in_seen(root: Path) -> None:
    seen: set[str] = set()

    plan_sync([_scanned(root / "A.txt"), _scanned(root / "b.jpg")], {}, _rules(IndexSource(path=root)), seen)

    assert seen == {path_key(root / "A.txt"), path_key(root / "b.jpg")}


def test_find_vanished_returns_cataloged_files_not_seen_this_scan(root: Path) -> None:
    snapshot = {
        **_cataloged(root / "gone.txt", CatalogStatus.INDEXED),
        **_cataloged(root / "here.txt", CatalogStatus.INDEXED),
    }

    vanished = find_vanished(snapshot, {path_key(root / "here.txt")}, _rules(IndexSource(path=root)))

    assert [e.path for e in vanished] == [root / "gone.txt"]


def test_find_vanished_keeps_files_under_a_temporarily_missing_source(root: Path, tmp_path: Path) -> None:
    unplugged = tmp_path / "USB"
    snapshot = _cataloged(unplugged / "photo.jpg", CatalogStatus.NAME_ONLY)

    vanished = find_vanished(snapshot, set(), _rules(IndexSource(path=root), IndexSource(path=unplugged)))

    assert vanished == []


def test_find_vanished_drops_files_of_a_source_that_was_removed(root: Path, tmp_path: Path) -> None:
    snapshot = _cataloged(tmp_path / "Old" / "a.txt", CatalogStatus.INDEXED)

    assert len(find_vanished(snapshot, set(), _rules(IndexSource(path=root)))) == 1


def test_target_status_is_pending_for_a_readable_file(root: Path) -> None:
    assert target_status(_scanned(root / "a.txt"), _rules(IndexSource(path=root))) is CatalogStatus.PENDING


def test_target_status_is_name_only_for_an_oversized_file(root: Path) -> None:
    oversized = _scanned(root / "a.txt", size=5000)

    assert target_status(oversized, _rules(IndexSource(path=root))) is CatalogStatus.NAME_ONLY
