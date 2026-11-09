"""
The single background thread that drains the index queue: indexes one file at a time,
records the outcome in the catalog, and pauses on request. Owns the worker loop and its
pause state only — choosing what gets queued is the index service's job.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from config.settings import get_settings
from core.exceptions import NimbusError, UnsupportedFileTypeError
from core.file_catalog import FileCatalog
from core.index_queue import IndexQueue
from core.indexer import Indexer
from core.logger import get_logger
from models.schema import CatalogStatus

logger = get_logger(__name__)

QUEUE_POLL_SECONDS = 0.5
STOP_JOIN_TIMEOUT_SECONDS = 10.0
# Folding new rows into the full-text index is cheap but not free; doing it every N files keeps
# keyword search fast during a long first index without slowing every single file down.
OPTIMIZE_EVERY_N_FILES = 200


class IndexWorker:
    """Pops files off the queue and indexes them until stopped."""

    def __init__(self, queue: IndexQueue, catalog: FileCatalog, indexer: Indexer) -> None:
        self._queue = queue
        self._catalog = catalog
        self._indexer = indexer
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = threading.Event()
        self._current_file: str | None = None
        self._since_optimize = 0

    @property
    def current_file(self) -> str | None:
        """Name of the file being indexed right now, for the progress display."""
        return self._current_file

    @property
    def is_paused(self) -> bool:
        return not self._running.is_set()

    def start(self) -> None:
        """Starts the worker thread, unpaused."""
        self._stop.clear()
        self._running.set()
        self._thread = threading.Thread(target=self._run, name="index-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Asks the loop to exit after the current file and waits for it."""
        self._stop.set()
        self._running.set()
        if self._thread is not None:
            self._thread.join(timeout=STOP_JOIN_TIMEOUT_SECONDS)
            self._thread = None

    def pause(self) -> None:
        """Stops picking up new files; the one in progress finishes first."""
        self._running.clear()
        logger.info("Indexing paused")

    def resume(self) -> None:
        self._running.set()
        logger.info("Indexing resumed")

    def _run(self) -> None:
        """The worker loop: wait while paused, index the next file, breathe, repeat."""
        throttle_seconds = get_settings().index_throttle_ms / 1000
        while not self._stop.is_set():
            self._running.wait()
            if self._stop.is_set():
                return
            path = self._queue.pop(timeout=QUEUE_POLL_SECONDS)
            if path is None:
                self._optimize_if_dirty(force=True)
                continue
            if self.is_paused:
                # Paused while we were waiting on the queue: put it back for after resume.
                self._queue.push(path, 0.0, urgent=True)
                continue
            self._index_one(path)
            self._optimize_if_dirty(force=False)
            time.sleep(throttle_seconds)

    def _index_one(self, path: Path) -> None:
        """Indexes one file and records the outcome; a single bad file never stops the loop."""
        if not path.is_file():
            # Deleted after it was queued; forget it rather than leave it pending forever.
            self._catalog.remove([path])
            return
        self._current_file = path.name
        try:
            self._indexer.index_file(path)
            self._catalog.set_status(path, CatalogStatus.INDEXED)
            self._since_optimize += 1
        except UnsupportedFileTypeError:
            self._catalog.set_status(path, CatalogStatus.NAME_ONLY)
        except NimbusError as e:
            logger.warning("Couldn't index file", extra={"path": str(path), "error": str(e)})
            self._catalog.set_status(path, CatalogStatus.FAILED, error=str(e)[:500])
        except Exception as e:
            # A library error nobody wrapped (or the file vanishing mid-index) must not kill the
            # only worker thread — that would silently stop all indexing until a restart.
            logger.exception("Unexpected error indexing file", extra={"path": str(path)})
            self._catalog.set_status(path, CatalogStatus.FAILED, error=str(e)[:500])
        finally:
            self._current_file = None

    def _optimize_if_dirty(self, force: bool) -> None:
        """Optimizes the store when the queue runs dry, or every OPTIMIZE_EVERY_N_FILES files."""
        if self._since_optimize == 0 or (not force and self._since_optimize < OPTIMIZE_EVERY_N_FILES):
            return
        self._since_optimize = 0
        self._indexer.optimize_store()
