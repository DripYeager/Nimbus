from __future__ import annotations

import logging
import time
from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from watchdog.events import DirCreatedEvent, FileCreatedEvent, FileDeletedEvent, FileMovedEvent

from core.exceptions import IndexingError, UnsupportedFileTypeError
from core.file_watcher import DEBOUNCE_SECONDS, FileWatcher, IndexingState, _WatchHandler
from core.indexer import Indexer
from core.vector_store import VectorStore

TEST_DEBOUNCE_SECONDS = 0.05
SETTLE_SECONDS = 0.15


def _watcher(mocker: MockerFixture) -> tuple[FileWatcher, Indexer, VectorStore, IndexingState]:
    indexer = mocker.Mock(spec=Indexer)
    store = mocker.Mock(spec=VectorStore)
    state = IndexingState()
    watcher = FileWatcher(indexer, store, state, debounce_seconds=TEST_DEBOUNCE_SECONDS)
    return watcher, indexer, store, state


def test_indexing_state_tracks_indexed_files_without_double_counting() -> None:
    state = IndexingState()
    state.mark_indexed("a.txt")
    state.mark_indexed("a.txt")
    state.mark_indexed("b.txt")

    assert state.indexed_files == 2


def test_indexing_state_mark_removed_drops_the_path() -> None:
    state = IndexingState()
    state.mark_indexed("a.txt")

    state.mark_removed("a.txt")

    assert state.indexed_files == 0


def test_indexing_state_total_files_is_indexed_plus_pending() -> None:
    state = IndexingState()
    state.mark_indexed("a.txt")
    state.pending_files = 2

    assert state.total_files == 3


def test_indexing_state_seed_adds_every_path() -> None:
    state = IndexingState()

    state.seed(["a.txt", "b.txt"])

    assert state.indexed_files == 2


def test_setup_skips_a_watched_directory_that_does_not_exist(mocker: MockerFixture, tmp_path: Path) -> None:
    watcher, _, _, _ = _watcher(mocker)
    missing = tmp_path / "does_not_exist"
    mocker.patch("core.file_watcher.get_settings", return_value=mocker.Mock(watched_dirs=[missing]))
    observer_cls = mocker.patch("core.file_watcher.Observer")

    watcher.setup()

    observer_cls.return_value.schedule.assert_not_called()


def test_setup_schedules_a_recursive_watch_for_each_existing_directory(mocker: MockerFixture, tmp_path: Path) -> None:
    watcher, _, _, _ = _watcher(mocker)
    mocker.patch("core.file_watcher.get_settings", return_value=mocker.Mock(watched_dirs=[tmp_path]))
    observer_cls = mocker.patch("core.file_watcher.Observer")

    watcher.setup()

    observer_cls.return_value.schedule.assert_called_once()
    args, kwargs = observer_cls.return_value.schedule.call_args
    assert args[1] == str(tmp_path)
    assert kwargs["recursive"] is True


def test_handle_changed_debounces_rapid_repeats_into_one_index_call(mocker: MockerFixture) -> None:
    watcher, indexer, _, _ = _watcher(mocker)
    path = Path("C:/Downloads/report.pdf")

    watcher.handle_changed(path)
    watcher.handle_changed(path)
    watcher.handle_changed(path)
    time.sleep(SETTLE_SECONDS)

    indexer.index_file.assert_called_once_with(path)


def test_handle_changed_processes_independent_paths_independently(mocker: MockerFixture) -> None:
    watcher, indexer, _, _ = _watcher(mocker)

    watcher.handle_changed(Path("C:/Downloads/a.pdf"))
    watcher.handle_changed(Path("C:/Downloads/b.pdf"))
    time.sleep(SETTLE_SECONDS)

    assert indexer.index_file.call_count == 2


def test_handle_changed_marks_the_path_indexed_after_processing(mocker: MockerFixture) -> None:
    watcher, _, _, state = _watcher(mocker)
    path = Path("C:/Downloads/report.pdf")

    watcher.handle_changed(path)
    time.sleep(SETTLE_SECONDS)

    assert state.indexed_files == 1


def test_handle_changed_drops_the_event_when_paused_at_fire_time(mocker: MockerFixture) -> None:
    watcher, indexer, _, state = _watcher(mocker)
    state.is_paused = True

    watcher.handle_changed(Path("C:/Downloads/report.pdf"))
    time.sleep(SETTLE_SECONDS)

    indexer.index_file.assert_not_called()


def test_handle_changed_still_processes_if_resumed_before_the_timer_fires(mocker: MockerFixture) -> None:
    watcher, indexer, _, state = _watcher(mocker)
    state.is_paused = True

    watcher.handle_changed(Path("C:/Downloads/report.pdf"))
    state.is_paused = False
    time.sleep(SETTLE_SECONDS)

    indexer.index_file.assert_called_once()


def test_handle_changed_logs_and_swallows_an_indexing_error(mocker: MockerFixture) -> None:
    watcher, indexer, _, state = _watcher(mocker)
    indexer.index_file.side_effect = IndexingError("boom")

    watcher.handle_changed(Path("C:/Downloads/report.pdf"))
    time.sleep(SETTLE_SECONDS)

    assert state.indexed_files == 0


def test_handle_changed_logs_an_unsupported_file_type_at_info_not_error(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    watcher, indexer, _, state = _watcher(mocker)
    indexer.index_file.side_effect = UnsupportedFileTypeError("no converter for .blend")

    with caplog.at_level(logging.INFO):
        watcher.handle_changed(Path("C:/Downloads/model.blend"))
        time.sleep(SETTLE_SECONDS)

    assert state.indexed_files == 0
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)
    assert any(record.levelno == logging.INFO for record in caplog.records)


def test_handle_removed_deletes_immediately_with_no_debounce(mocker: MockerFixture) -> None:
    watcher, _, store, state = _watcher(mocker)
    state.mark_indexed(str(Path("C:/Downloads/report.pdf")))

    watcher.handle_removed(Path("C:/Downloads/report.pdf"))

    store.delete_by_path.assert_called_once_with(str(Path("C:/Downloads/report.pdf")))
    assert state.indexed_files == 0
    assert watcher._timers == {}


def test_handle_removed_drops_the_event_when_paused(mocker: MockerFixture) -> None:
    watcher, _, store, state = _watcher(mocker)
    state.is_paused = True

    watcher.handle_removed(Path("C:/Downloads/report.pdf"))

    store.delete_by_path.assert_not_called()


def test_stop_cancels_pending_timers_so_they_never_fire(mocker: MockerFixture) -> None:
    watcher, indexer, _, _ = _watcher(mocker)
    watcher._observer = mocker.Mock()
    watcher.handle_changed(Path("C:/Downloads/report.pdf"))

    watcher.stop()
    time.sleep(SETTLE_SECONDS)

    indexer.index_file.assert_not_called()
    watcher._observer.stop.assert_called_once()
    watcher._observer.join.assert_called_once()


def test_watch_handler_on_created_ignores_directory_events(mocker: MockerFixture) -> None:
    watcher, indexer, _, _ = _watcher(mocker)
    handler = _WatchHandler(watcher)

    handler.on_created(DirCreatedEvent(src_path="C:/Downloads/sub"))
    time.sleep(SETTLE_SECONDS)

    indexer.index_file.assert_not_called()


def test_watch_handler_on_created_forwards_file_events(mocker: MockerFixture) -> None:
    watcher, indexer, _, _ = _watcher(mocker)
    handler = _WatchHandler(watcher)

    handler.on_created(FileCreatedEvent(src_path="C:/Downloads/new.pdf"))
    time.sleep(SETTLE_SECONDS)

    indexer.index_file.assert_called_once_with(Path("C:/Downloads/new.pdf"))


def test_watch_handler_on_deleted_forwards_to_handle_removed(mocker: MockerFixture) -> None:
    watcher, _, store, _ = _watcher(mocker)
    handler = _WatchHandler(watcher)

    handler.on_deleted(FileDeletedEvent(src_path="C:/Downloads/gone.pdf"))

    store.delete_by_path.assert_called_once_with(str(Path("C:/Downloads/gone.pdf")))


def test_watch_handler_on_moved_deletes_the_old_path_and_reindexes_the_new_one(mocker: MockerFixture) -> None:
    watcher, indexer, store, _ = _watcher(mocker)
    handler = _WatchHandler(watcher)

    handler.on_moved(FileMovedEvent(src_path="C:/Downloads/old.pdf", dest_path="C:/Downloads/new.pdf"))
    time.sleep(SETTLE_SECONDS)

    store.delete_by_path.assert_called_once_with(str(Path("C:/Downloads/old.pdf")))
    indexer.index_file.assert_called_once_with(Path("C:/Downloads/new.pdf"))


def test_debounce_seconds_defaults_to_the_module_constant(mocker: MockerFixture) -> None:
    indexer = mocker.Mock(spec=Indexer)
    store = mocker.Mock(spec=VectorStore)
    watcher = FileWatcher(indexer, store, IndexingState())

    assert watcher._debounce_seconds == DEBOUNCE_SECONDS
