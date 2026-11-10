from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

import config.settings as settings_module
from config.settings import Settings
from core.exceptions import ParsingError, UnsupportedFileTypeError
from core.file_catalog import FileCatalog, path_key
from core.index_queue import IndexQueue
from core.index_worker import IndexWorker
from core.indexer import Indexer
from models.schema import CatalogEntry, CatalogStatus

POLL_SECONDS = 0.02


@pytest.fixture(autouse=True)
def _fast_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_module, "_settings", Settings(_env_file=None, index_throttle_ms=0))
    monkeypatch.setattr("core.index_worker.QUEUE_POLL_SECONDS", POLL_SECONDS)


@pytest.fixture
def catalog(tmp_path: Path) -> Iterator[FileCatalog]:
    opened = FileCatalog(tmp_path / "catalog.db")
    opened.connect()
    yield opened
    opened.close()


@pytest.fixture
def indexer(mocker: MockerFixture) -> Mock:
    return mocker.Mock(spec=Indexer)


@pytest.fixture
def queue() -> IndexQueue:
    return IndexQueue()


@pytest.fixture
def worker(queue: IndexQueue, catalog: FileCatalog, indexer: Mock) -> Iterator[IndexWorker]:
    started = IndexWorker(queue, catalog, indexer)
    started.start()
    yield started
    started.stop()


def _wait_until(condition: Callable[[], bool], timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


def _add_file(tmp_path: Path, catalog: FileCatalog, queue: IndexQueue, name: str, mtime: float = 1.0) -> Path:
    path = tmp_path / name
    path.write_text("contents", encoding="utf-8")
    catalog.upsert([CatalogEntry(path, 8, mtime, CatalogStatus.PENDING)])
    queue.push(path, mtime)
    return path


def _status(catalog: FileCatalog, path: Path) -> CatalogStatus:
    return catalog.snapshot()[path_key(path)].status


def _has_status(catalog: FileCatalog, path: Path, status: CatalogStatus) -> Callable[[], bool]:
    return lambda: _status(catalog, path) is status


def test_worker_marks_a_successfully_indexed_file_indexed(
    worker: IndexWorker, tmp_path: Path, catalog: FileCatalog, queue: IndexQueue
) -> None:
    path = _add_file(tmp_path, catalog, queue, "a.txt")

    assert _wait_until(_has_status(catalog, path, CatalogStatus.INDEXED))


def test_worker_marks_an_unsupported_file_name_only(
    worker: IndexWorker, tmp_path: Path, catalog: FileCatalog, queue: IndexQueue, indexer: Mock
) -> None:
    indexer.index_file.side_effect = UnsupportedFileTypeError("no converter")

    path = _add_file(tmp_path, catalog, queue, "model.blend")

    assert _wait_until(_has_status(catalog, path, CatalogStatus.NAME_ONLY))


def test_worker_marks_a_file_that_fails_to_parse_failed(
    worker: IndexWorker, tmp_path: Path, catalog: FileCatalog, queue: IndexQueue, indexer: Mock
) -> None:
    indexer.index_file.side_effect = ParsingError("encrypted")

    path = _add_file(tmp_path, catalog, queue, "locked.pdf")

    assert _wait_until(_has_status(catalog, path, CatalogStatus.FAILED))


@pytest.mark.parametrize("error", [ParsingError("encrypted"), RuntimeError("library bug")])
def test_worker_keeps_going_after_a_file_fails(
    worker: IndexWorker, tmp_path: Path, catalog: FileCatalog, queue: IndexQueue, indexer: Mock, error: Exception
) -> None:
    def index_file(path: Path) -> int:
        if path.name == "bad.pdf":
            raise error
        return 1

    indexer.index_file.side_effect = index_file
    _add_file(tmp_path, catalog, queue, "bad.pdf", mtime=2.0)

    good = _add_file(tmp_path, catalog, queue, "good.txt", mtime=1.0)

    assert _wait_until(_has_status(catalog, good, CatalogStatus.INDEXED))


def test_worker_skips_a_file_deleted_before_its_turn(
    worker: IndexWorker, tmp_path: Path, catalog: FileCatalog, queue: IndexQueue, indexer: Mock
) -> None:
    queue.push(tmp_path / "deleted.txt", modified_ts=2.0)

    path = _add_file(tmp_path, catalog, queue, "a.txt", mtime=1.0)

    assert _wait_until(_has_status(catalog, path, CatalogStatus.INDEXED))
    indexer.index_file.assert_called_once_with(path)


def test_worker_reports_the_file_it_is_indexing(
    worker: IndexWorker, tmp_path: Path, catalog: FileCatalog, queue: IndexQueue, indexer: Mock
) -> None:
    seen: list[Path | None] = []
    indexer.index_file.side_effect = lambda path: seen.append(worker.current_path)

    path = _add_file(tmp_path, catalog, queue, "report.docx")

    assert _wait_until(_has_status(catalog, path, CatalogStatus.INDEXED))
    assert seen == [path]
    assert worker.current_path is None


def test_worker_optimizes_the_store_once_the_queue_runs_dry(
    worker: IndexWorker, tmp_path: Path, catalog: FileCatalog, queue: IndexQueue, indexer: Mock
) -> None:
    _add_file(tmp_path, catalog, queue, "a.txt")

    assert _wait_until(lambda: indexer.optimize_store.called)


def test_worker_does_not_optimize_when_nothing_was_indexed(worker: IndexWorker, indexer: Mock) -> None:
    time.sleep(POLL_SECONDS * 5)

    indexer.optimize_store.assert_not_called()


def test_pause_stops_new_files_being_picked_up(
    worker: IndexWorker, tmp_path: Path, catalog: FileCatalog, queue: IndexQueue, indexer: Mock
) -> None:
    worker.pause()
    time.sleep(POLL_SECONDS * 3)

    _add_file(tmp_path, catalog, queue, "a.txt")
    time.sleep(POLL_SECONDS * 5)

    assert worker.is_paused is True
    indexer.index_file.assert_not_called()


def test_resume_picks_up_where_pause_left_off(
    worker: IndexWorker, tmp_path: Path, catalog: FileCatalog, queue: IndexQueue
) -> None:
    worker.pause()
    time.sleep(POLL_SECONDS * 3)
    path = _add_file(tmp_path, catalog, queue, "a.txt")

    worker.resume()

    assert worker.is_paused is False
    assert _wait_until(_has_status(catalog, path, CatalogStatus.INDEXED))


def test_stop_returns_promptly_and_ends_the_thread(queue: IndexQueue, catalog: FileCatalog, indexer: Mock) -> None:
    worker = IndexWorker(queue, catalog, indexer)
    worker.start()
    thread = worker._thread

    started = time.monotonic()
    worker.stop()

    assert time.monotonic() - started < 2.0
    assert not thread.is_alive()


def test_stop_returns_while_paused(queue: IndexQueue, catalog: FileCatalog, indexer: Mock) -> None:
    worker = IndexWorker(queue, catalog, indexer)
    worker.start()
    worker.pause()
    thread = worker._thread

    worker.stop()

    assert not thread.is_alive()


def test_stop_is_safe_before_start(queue: IndexQueue, catalog: FileCatalog, indexer: Mock) -> None:
    IndexWorker(queue, catalog, indexer).stop()
