"""
Watches the configured directories for file changes and forwards debounced, stable paths to
the indexer — a burst of rapid saves collapses into one reindex. Also defines IndexingState,
the shared pause/count state the tray and API read to build IndexStatus. Does not parse or
embed anything itself; it only decides what needs (re)indexing and when.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from config.settings import get_settings
from core.exceptions import NimbusError, UnsupportedFileTypeError
from core.indexer import Indexer
from core.logger import get_logger
from core.vector_store import VectorStore

logger = get_logger(__name__)

DEBOUNCE_SECONDS = 3.0


class IndexingState:
    """Tracks pause state and the indexed/pending file counts the tray and API report. The
    watcher is the only writer; api/server.py only reads it to build IndexStatus."""

    def __init__(self) -> None:
        self.is_paused = False
        self.pending_files = 0
        self._indexed_paths: set[str] = set()

    @property
    def indexed_files(self) -> int:
        """Distinct files currently represented in the index, as tracked by the watcher."""
        return len(self._indexed_paths)

    @property
    def total_files(self) -> int:
        """Files the watcher currently knows about: already indexed plus still pending."""
        return self.indexed_files + self.pending_files

    def mark_indexed(self, path: str) -> None:
        """Records path as indexed — safe to call repeatedly for the same path."""
        self._indexed_paths.add(path)

    def mark_removed(self, path: str) -> None:
        """Drops path from the indexed set — called on delete or move-away."""
        self._indexed_paths.discard(path)

    def seed(self, paths: Iterable[str]) -> None:
        """Seeds the indexed set from an initial full-index pass at startup."""
        self._indexed_paths.update(paths)


class FileWatcher:
    """Wraps watchdog: observes the configured directories and debounces bursts of file events
    before forwarding stable paths to the indexer.

    While indexing_state.is_paused is set, every event is dropped rather than queued — pausing
    is meant to make Nimbus fully idle during a sensitive task, and queueing would mean a burst
    of reindexing fires the moment the user resumes, defeating the point of pausing at all. A
    file changed while paused is simply picked up the next time it changes, or by a rebuild.
    """

    def __init__(
        self,
        indexer: Indexer,
        store: VectorStore,
        indexing_state: IndexingState,
        debounce_seconds: float = DEBOUNCE_SECONDS,
    ) -> None:
        self._indexer = indexer
        self._store = store
        self._state = indexing_state
        self._debounce_seconds = debounce_seconds
        self._observer: Observer | None = None
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def setup(self) -> None:
        """Schedules a recursive watch on every configured directory that actually exists."""
        self._observer = Observer()
        handler = _WatchHandler(self)
        for directory in get_settings().watched_dirs:
            if not directory.is_dir():
                logger.warning("Watched directory doesn't exist, skipping", extra={"path": str(directory)})
                continue
            self._observer.schedule(handler, str(directory), recursive=True)

    def start(self) -> None:
        """Starts the observer's own background thread — returns immediately."""
        self._observer.start()
        logger.info("File watcher started")

    def stop(self) -> None:
        """Stops the observer and cancels every pending debounce timer."""
        self._observer.stop()
        self._observer.join()
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
        logger.info("File watcher stopped")

    def handle_changed(self, path: Path) -> None:
        """(Re)starts path's debounce timer — a rapid burst of saves collapses into one reindex."""
        with self._lock:
            existing = self._timers.get(str(path))
            if existing is not None:
                existing.cancel()
            timer = threading.Timer(self._debounce_seconds, self._process_changed, args=(path,))
            timer.daemon = True
            self._timers[str(path)] = timer
            self._state.pending_files = len(self._timers)
            timer.start()

    def handle_removed(self, path: Path) -> None:
        """Removes path's rows immediately — deletes aren't debounced, there's nothing to collapse."""
        if self._state.is_paused:
            logger.info("Dropping delete event while paused", extra={"path": str(path)})
            return
        try:
            self._store.delete_by_path(str(path))
            self._state.mark_removed(str(path))
        except NimbusError as e:
            logger.error("Failed to remove deleted file from the index", extra={"path": str(path), "error": str(e)})

    def _process_changed(self, path: Path) -> None:
        """Runs once the debounce window elapses; drops the event entirely if paused."""
        with self._lock:
            self._timers.pop(str(path), None)
            self._state.pending_files = len(self._timers)
        if self._state.is_paused:
            logger.info("Dropping change event while paused", extra={"path": str(path)})
            return
        try:
            self._indexer.index_file(path)
            self._state.mark_indexed(str(path))
        except UnsupportedFileTypeError as e:
            logger.info("Skipping file with no available converter", extra={"path": str(path), "error": str(e)})
        except NimbusError as e:
            logger.error("Failed to index changed file", extra={"path": str(path), "error": str(e)})


class _WatchHandler(FileSystemEventHandler):
    """Translates raw watchdog events into FileWatcher calls, ignoring directory events."""

    def __init__(self, watcher: FileWatcher) -> None:
        self._watcher = watcher

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._watcher.handle_changed(Path(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._watcher.handle_changed(Path(event.src_path))

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._watcher.handle_removed(Path(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._watcher.handle_removed(Path(event.src_path))
        self._watcher.handle_changed(Path(event.dest_path))
