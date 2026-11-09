from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture
from watchdog.events import (
    DirCreatedEvent,
    DirModifiedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
)

from core.file_watcher import DEBOUNCE_SECONDS, FileWatcher, _WatchHandler
from models.schema import IndexSource

TEST_DEBOUNCE_SECONDS = 0.05
# Long enough for any stray timer to have fired, so "it didn't happen" is a real observation.
QUIET_SECONDS = TEST_DEBOUNCE_SECONDS * 3
WAIT_SECONDS = 5.0


class RecordingSink:
    """Collects what the watcher forwards and lets a test wait for it without sleeping blindly."""

    def __init__(self) -> None:
        self.changed: list[Path] = []
        self.removed: list[Path] = []
        self.arrived = threading.Event()

    def path_changed(self, path: Path) -> None:
        self.changed.append(path)
        self.arrived.set()

    def path_removed(self, path: Path) -> None:
        self.removed.append(path)
        self.arrived.set()


@pytest.fixture
def sink() -> RecordingSink:
    return RecordingSink()


@pytest.fixture
def watcher(sink: RecordingSink) -> Iterator[FileWatcher]:
    created = FileWatcher(sink, debounce_seconds=TEST_DEBOUNCE_SECONDS)
    yield created
    created.stop()


@pytest.fixture
def observer_cls(mocker: MockerFixture) -> Mock:
    return mocker.patch("core.file_watcher.Observer")


def test_file_watcher_defaults_to_the_module_debounce(sink: RecordingSink) -> None:
    assert FileWatcher(sink)._debounce_seconds == DEBOUNCE_SECONDS


def test_handle_changed_collapses_a_burst_of_saves_into_one_event(watcher: FileWatcher, sink: RecordingSink) -> None:
    path = Path("C:/Docs/report.docx")

    for _ in range(3):
        watcher.handle_changed(path)

    assert sink.arrived.wait(WAIT_SECONDS)
    time.sleep(QUIET_SECONDS)
    assert sink.changed == [path]


def test_handle_changed_forwards_independent_paths_separately(watcher: FileWatcher, sink: RecordingSink) -> None:
    watcher.handle_changed(Path("C:/Docs/a.txt"))
    watcher.handle_changed(Path("C:/Docs/b.txt"))

    time.sleep(QUIET_SECONDS)

    assert sorted(sink.changed) == [Path("C:/Docs/a.txt"), Path("C:/Docs/b.txt")]


def test_handle_removed_forwards_immediately(watcher: FileWatcher, sink: RecordingSink) -> None:
    watcher.handle_removed(Path("C:/Docs/gone.txt"))

    assert sink.removed == [Path("C:/Docs/gone.txt")]


def test_handle_removed_cancels_a_pending_change_for_the_same_path(watcher: FileWatcher, sink: RecordingSink) -> None:
    path = Path("C:/Docs/temp.txt")
    watcher.handle_changed(path)

    watcher.handle_removed(path)
    time.sleep(QUIET_SECONDS)

    assert sink.changed == []


def test_a_failing_sink_is_logged_not_raised(
    watcher: FileWatcher, sink: RecordingSink, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    mocker.patch.object(sink, "path_removed", side_effect=RuntimeError("catalog locked"))

    with caplog.at_level(logging.ERROR):
        watcher.handle_removed(Path("C:/Docs/gone.txt"))

    assert any(record.levelno == logging.ERROR for record in caplog.records)


def test_start_watches_each_existing_source_recursively(
    watcher: FileWatcher, observer_cls: Mock, tmp_path: Path
) -> None:
    watcher.start([IndexSource(path=tmp_path)])

    observer_cls.return_value.schedule.assert_called_once()
    args, kwargs = observer_cls.return_value.schedule.call_args
    assert (args[1], kwargs) == (str(tmp_path), {"recursive": True})


def test_start_skips_a_source_folder_that_does_not_exist(
    watcher: FileWatcher, observer_cls: Mock, tmp_path: Path
) -> None:
    watcher.start([IndexSource(path=tmp_path / "unplugged")])

    observer_cls.return_value.schedule.assert_not_called()
    observer_cls.return_value.start.assert_called_once()


def test_stop_cancels_pending_timers_so_they_never_fire(
    watcher: FileWatcher, sink: RecordingSink, observer_cls: Mock, tmp_path: Path
) -> None:
    watcher.start([IndexSource(path=tmp_path)])
    watcher.handle_changed(Path("C:/Docs/report.docx"))

    watcher.stop()
    time.sleep(QUIET_SECONDS)

    assert sink.changed == []
    observer_cls.return_value.join.assert_called_once()


def test_stop_is_safe_to_call_twice(watcher: FileWatcher, observer_cls: Mock, tmp_path: Path) -> None:
    watcher.start([IndexSource(path=tmp_path)])

    watcher.stop()
    watcher.stop()

    observer_cls.return_value.stop.assert_called_once()


def test_restart_watches_the_new_set_of_folders(watcher: FileWatcher, observer_cls: Mock, tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    watcher.start([IndexSource(path=first)])

    watcher.restart([IndexSource(path=second)])

    assert observer_cls.return_value.schedule.call_args.args[1] == str(second)


def test_watcher_reports_a_real_file_created_in_a_source(
    watcher: FileWatcher, sink: RecordingSink, tmp_path: Path
) -> None:
    watcher.start([IndexSource(path=tmp_path)])
    created = tmp_path / "new.txt"

    created.write_text("hello", encoding="utf-8")

    assert sink.arrived.wait(WAIT_SECONDS)
    assert created in sink.changed


def test_watch_handler_forwards_a_created_folder_for_scanning(watcher: FileWatcher, mocker: MockerFixture) -> None:
    changed = mocker.patch.object(watcher, "handle_changed")

    _WatchHandler(watcher).on_created(DirCreatedEvent(src_path="C:/Docs/Imported"))

    changed.assert_called_once_with(Path("C:/Docs/Imported"))


def test_watch_handler_forwards_a_modified_file(watcher: FileWatcher, mocker: MockerFixture) -> None:
    changed = mocker.patch.object(watcher, "handle_changed")

    _WatchHandler(watcher).on_modified(FileModifiedEvent(src_path="C:/Docs/a.txt"))

    changed.assert_called_once_with(Path("C:/Docs/a.txt"))


def test_watch_handler_ignores_a_folder_modified_event(watcher: FileWatcher, mocker: MockerFixture) -> None:
    changed = mocker.patch.object(watcher, "handle_changed")

    _WatchHandler(watcher).on_modified(DirModifiedEvent(src_path="C:/Docs"))

    changed.assert_not_called()


def test_watch_handler_forwards_a_deleted_file(watcher: FileWatcher, mocker: MockerFixture) -> None:
    removed = mocker.patch.object(watcher, "handle_removed")

    _WatchHandler(watcher).on_deleted(FileDeletedEvent(src_path="C:/Docs/gone.txt"))

    removed.assert_called_once_with(Path("C:/Docs/gone.txt"))


def test_watch_handler_treats_a_move_as_remove_then_change(watcher: FileWatcher, mocker: MockerFixture) -> None:
    removed = mocker.patch.object(watcher, "handle_removed")
    changed = mocker.patch.object(watcher, "handle_changed")

    _WatchHandler(watcher).on_moved(FileMovedEvent(src_path="C:/Docs/old.txt", dest_path="C:/Docs/new.txt"))

    removed.assert_called_once_with(Path("C:/Docs/old.txt"))
    changed.assert_called_once_with(Path("C:/Docs/new.txt"))


def test_watch_handler_forwards_a_created_file(watcher: FileWatcher, mocker: MockerFixture) -> None:
    changed = mocker.patch.object(watcher, "handle_changed")

    _WatchHandler(watcher).on_created(FileCreatedEvent(src_path="C:/Docs/new.txt"))

    changed.assert_called_once_with(Path("C:/Docs/new.txt"))


def test_handle_changed_uses_one_thread_for_a_flood_of_paths(watcher: FileWatcher, sink: RecordingSink) -> None:
    threads_before = threading.active_count()

    for index in range(500):
        watcher.handle_changed(Path(f"C:/Docs/node_modules/pkg{index}/index.js"))

    assert threading.active_count() <= threads_before + 1
    deadline = time.monotonic() + WAIT_SECONDS
    while len(sink.changed) < 500 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(sink.changed) == 500
