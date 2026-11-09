"""
Watches the user's source folders for changes and forwards debounced paths to the index
service — a burst of rapid saves collapses into one reindex. Does not decide what a change
means for the index; it only reports which paths changed or disappeared, and when.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from core.logger import get_logger
from models.schema import IndexSource

logger = get_logger(__name__)

DEBOUNCE_SECONDS = 3.0
STOP_JOIN_TIMEOUT_SECONDS = 5.0


class ChangeSink(Protocol):
    """Whatever wants to hear about changes — the index service, in the real app."""

    def path_changed(self, path: Path) -> None: ...

    def path_removed(self, path: Path) -> None: ...


class FileWatcher:
    """Wraps watchdog: observes the source folders and debounces bursts of events per path.

    One debounce thread serves every path. A per-path timer thread would be simpler, but an
    `npm install` or an unzipped archive inside a source creates tens of thousands of files in
    seconds — one thread each would exhaust the process."""

    def __init__(self, sink: ChangeSink, debounce_seconds: float = DEBOUNCE_SECONDS) -> None:
        self._sink = sink
        self._debounce_seconds = debounce_seconds
        self._observer: Observer | None = None
        self._pending: dict[str, tuple[Path, float]] = {}
        self._condition = threading.Condition()
        self._debouncer: threading.Thread | None = None
        self._stopping = False

    def start(self, sources: list[IndexSource]) -> None:
        """Starts a recursive watch on every source folder that exists. Returns immediately."""
        with self._condition:
            self._stopping = False
        self._observer = Observer()
        handler = _WatchHandler(self)
        for source in sources:
            if not source.path.is_dir():
                logger.warning("Source folder doesn't exist, not watching it", extra={"path": str(source.path)})
                continue
            self._observer.schedule(handler, str(source.path), recursive=True)
        self._observer.start()
        logger.info("File watcher started", extra={"folders": len(sources)})

    def stop(self) -> None:
        """Stops the observer and drops every pending change. Safe to call twice."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        with self._condition:
            self._stopping = True
            self._pending.clear()
            self._condition.notify_all()
        if self._debouncer is not None:
            self._debouncer.join(timeout=STOP_JOIN_TIMEOUT_SECONDS)
            self._debouncer = None

    def restart(self, sources: list[IndexSource]) -> None:
        """Re-watches a new set of folders after the user changes their sources."""
        self.stop()
        self.start(sources)

    def handle_changed(self, path: Path) -> None:
        """(Re)starts path's debounce window — a rapid burst of saves collapses into one event."""
        with self._condition:
            if self._stopping:
                return
            self._pending[str(path)] = (path, time.monotonic() + self._debounce_seconds)
            self._ensure_debouncer()
            self._condition.notify()

    def handle_removed(self, path: Path) -> None:
        """Forwards a delete immediately — there's nothing to collapse, and a pending change
        for the same path would only try to index a file that's gone."""
        with self._condition:
            self._pending.pop(str(path), None)
        self._forward(self._sink.path_removed, path)

    def _ensure_debouncer(self) -> None:
        """Starts the debounce thread on first use. Caller holds the condition."""
        if self._debouncer is None or not self._debouncer.is_alive():
            self._debouncer = threading.Thread(target=self._run_debouncer, name="watch-debounce", daemon=True)
            self._debouncer.start()

    def _run_debouncer(self) -> None:
        """Forwards each path once its window has passed, sleeping until the next one is due."""
        while True:
            with self._condition:
                if self._stopping:
                    return
                due, wait_seconds = self._take_due_paths()
                if not due:
                    self._condition.wait(timeout=wait_seconds)
                    continue
            for path in due:
                self._forward(self._sink.path_changed, path)

    def _take_due_paths(self) -> tuple[list[Path], float | None]:
        """Removes and returns the paths whose window has passed, plus how long until the next
        one is due (None when nothing is pending). Caller holds the condition."""
        now = time.monotonic()
        due_keys = [key for key, (_, deadline) in self._pending.items() if deadline <= now]
        due = [self._pending.pop(key)[0] for key in due_keys]
        next_deadline = min((deadline for _, deadline in self._pending.values()), default=None)
        return due, None if next_deadline is None else max(0.0, next_deadline - now)

    def _forward(self, callback: Callable[[Path], None], path: Path) -> None:
        """Calls the sink, logging failures — a watcher thread that dies stops all future updates."""
        try:
            callback(path)
        except Exception:
            logger.exception("Failed to process a file change", extra={"path": str(path)})


class _WatchHandler(FileSystemEventHandler):
    """Translates raw watchdog events into FileWatcher calls. Folder creations and moves are
    forwarded too, so a folder dragged into a source gets scanned as a whole."""

    def __init__(self, watcher: FileWatcher) -> None:
        self._watcher = watcher

    def on_created(self, event: FileSystemEvent) -> None:
        self._watcher.handle_changed(Path(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        # A folder's own "modified" event just means its listing changed; the files inside
        # report themselves.
        if not event.is_directory:
            self._watcher.handle_changed(Path(event.src_path))

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._watcher.handle_removed(Path(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        self._watcher.handle_removed(Path(event.src_path))
        self._watcher.handle_changed(Path(event.dest_path))
