"""
Runs indexing for the whole app: scans the user's sources into the file catalog, queues
changed files for content indexing, reacts to watcher events and settings changes, and
reports progress. Coordinates the catalog, queue, worker and vector store — it never parses,
embeds or stores anything itself.
"""

from __future__ import annotations

import threading
from pathlib import Path

from config.settings import get_settings
from core.catalog_sync import find_vanished, plan_sync
from core.directory_scanner import scan_source
from core.file_catalog import FileCatalog, path_key
from core.index_queue import IndexQueue
from core.index_rules import IndexRules
from core.index_worker import IndexWorker
from core.indexer import Indexer
from core.logger import get_logger
from core.vector_store import VectorStore
from models.schema import CatalogEntry, CatalogStatus, IndexStatus, ScannedFile, SourceSummary, SyncPlan

logger = get_logger(__name__)


class IndexService:
    """The one place the rest of the app goes to change or ask about indexing."""

    def __init__(self, catalog: FileCatalog, store: VectorStore, indexer: Indexer) -> None:
        self._catalog = catalog
        self._store = store
        self._queue = IndexQueue()
        self._worker = IndexWorker(self._queue, catalog, indexer)
        self._rules = IndexRules.from_settings(get_settings())
        self._scan_lock = threading.Lock()
        self._rescan_requested = threading.Event()
        self._is_scanning = False

    @property
    def rules(self) -> IndexRules:
        return self._rules

    def start(self, embedding_model: str) -> None:
        """Re-queues anything left pending last session, starts the worker, and kicks off a
        background rescan. Returns immediately — nothing here blocks the app from opening."""
        if self._store.ensure_compatible(embedding_model):
            self._catalog.requeue_all()
        for path, modified_ts in self._catalog.pending_files():
            self._queue.push(path, modified_ts)
        self._worker.start()
        self.rescan()

    def stop(self) -> None:
        self._worker.stop()

    def rescan(self) -> None:
        """Rescans every source on a background thread. If a scan is already running, it runs
        once more when it finishes, so a folder added mid-scan isn't missed."""
        self._rescan_requested.set()
        threading.Thread(target=self._scan_all_sources, name="index-scan", daemon=True).start()

    def rebuild(self) -> None:
        """Re-reads every file's contents from scratch, e.g. after a parser upgrade. The stored
        chunks are dropped first — otherwise the indexer's unchanged-contents check would skip
        every file and the rebuild would re-read nothing."""
        self._queue.clear()
        self._store.drop_all()
        self._catalog.requeue_all()
        for path, modified_ts in self._catalog.pending_files():
            self._queue.push(path, modified_ts)
        self.rescan()

    def apply_settings(self) -> None:
        """Picks up changed sources/file types: purges removed folders right away, then rescans
        so newly allowed or newly excluded files settle into the right state."""
        new_rules = IndexRules.from_settings(get_settings())
        kept = {s.path for s in new_rules.sources}
        for removed in (s.path for s in self._rules.sources if s.path not in kept):
            self._purge_folder(removed)
        self._rules = new_rules
        self.rescan()

    def path_changed(self, path: Path) -> None:
        """Watcher hook for a created/modified/moved-in path. A folder gets its subtree scanned."""
        if path.is_dir():
            # A new node_modules (or any excluded folder) would otherwise be walked in full only
            # for every file in it to be thrown away.
            if not self._rules.is_covered(path) or self._is_excluded_subfolder(path):
                return
            self._apply_plan(plan_sync(scan_source(path, self._rules), self._catalog.snapshot(), self._rules, set()))
            return
        if not path.is_file() or not self._rules.is_covered(path):
            return
        stat = path.stat()
        scanned = ScannedFile(path=path, size_bytes=stat.st_size, modified_ts=stat.st_mtime)
        existing = self._catalog.entry_for(path)
        snapshot = {path_key(path): existing} if existing is not None else {}
        # Same decision logic as a full scan, so e.g. a file that just outgrew the size limit
        # loses its content rows here too.
        self._apply_plan(plan_sync([scanned], snapshot, self._rules, set()), urgent=True)

    def path_removed(self, path: Path) -> None:
        """Watcher hook for a deleted/moved-away path — a file, or a whole folder."""
        self._queue.discard(path)
        self._catalog.remove([path])
        self._store.delete_by_path(str(path))
        self._purge_folder(path)

    def set_paused(self, paused: bool) -> None:
        if paused:
            self._worker.pause()
        else:
            self._worker.resume()

    def status(self) -> IndexStatus:
        """A snapshot of progress for the tray, the chat header and Settings."""
        counts = self._catalog.status_counts()
        indexed = counts.get(CatalogStatus.INDEXED, 0)
        pending = counts.get(CatalogStatus.PENDING, 0)
        failed = counts.get(CatalogStatus.FAILED, 0)
        return IndexStatus(
            cataloged_files=sum(counts.values()),
            content_files=indexed + pending + failed,
            indexed_files=indexed,
            pending_files=pending,
            failed_files=failed,
            is_paused=self._worker.is_paused,
            is_scanning=self._is_scanning,
            current_file=self._worker.current_file,
        )

    def source_summaries(self) -> list[SourceSummary]:
        """Per-folder counts for the Settings window."""
        summaries = []
        for source in self._rules.sources:
            total, indexed = self._catalog.count_under(source.path)
            summaries.append(
                SourceSummary(
                    path=str(source.path),
                    include_contents=source.include_contents,
                    exists=source.path.is_dir(),
                    file_count=total,
                    indexed_count=indexed,
                )
            )
        return summaries

    def _scan_all_sources(self) -> None:
        """Walks every source, applies each one's changes as soon as it's scanned (so name
        search works for the first folder before the last one is done), then drops vanished files."""
        if not self._scan_lock.acquire(blocking=False):
            return
        self._is_scanning = True
        try:
            self._rescan_requested.clear()
            self._scan_once()
            # A rescan asked for while this one ran (a source added mid-scan) gets its own pass.
            while self._rescan_requested.is_set():
                self._rescan_requested.clear()
                self._scan_once()
        except Exception:
            logger.exception("Source scan failed")
        finally:
            self._is_scanning = False
            self._scan_lock.release()

    def _scan_once(self) -> None:
        """One full pass over every source."""
        snapshot = self._catalog.snapshot()
        seen: set[str] = set()
        for source in self._rules.sources:
            if source.path.is_dir():
                self._apply_plan(plan_sync(scan_source(source.path, self._rules), snapshot, self._rules, seen))
        self._drop_vanished(find_vanished(snapshot, seen, self._rules))
        logger.info("Source scan complete", extra={"files_seen": len(seen), "queued": len(self._queue)})

    def _apply_plan(self, plan: SyncPlan, urgent: bool = False) -> None:
        """Writes one scan's decisions to the catalog, queue and store. urgent puts the queued
        files ahead of everything else — for files the user just touched."""
        self._catalog.upsert(plan.upserts)
        for path, modified_ts in plan.to_queue:
            self._queue.push(path, modified_ts, urgent=urgent)
        for path in plan.drop_content:
            self._queue.discard(path)
        if plan.drop_content:
            self._store.delete_by_paths([str(p) for p in plan.drop_content])

    def _drop_vanished(self, vanished: list[CatalogEntry]) -> None:
        """Forgets files that no longer exist (or are now excluded) everywhere they're recorded."""
        if not vanished:
            return
        for entry in vanished:
            self._queue.discard(entry.path)
        self._catalog.remove(e.path for e in vanished)
        # A pending or failed file can still hold rows from an earlier successful index.
        with_content = [str(e.path) for e in vanished if e.status is not CatalogStatus.NAME_ONLY]
        self._store.delete_by_paths(with_content)
        logger.info("Removed vanished files", extra={"count": len(vanished)})

    def _is_excluded_subfolder(self, directory: Path) -> bool:
        """True for an excluded folder below a source root (a root the user picked always counts)."""
        source = self._rules.source_for(directory)
        return source is not None and directory != source.path and self._rules.is_excluded_dir(directory)

    def _purge_folder(self, root: Path) -> None:
        """Drops a whole folder from the queue, catalog and store in three bulk operations."""
        self._queue.discard_under(root)
        self._catalog.remove_under(root)
        self._store.delete_under(root)
