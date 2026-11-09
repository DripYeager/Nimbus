"""
The file catalog: a small SQLite table of every file in the user's sources — name, size,
modified time, and where it is in the content-indexing pipeline. Makes every file findable by
name within seconds of first launch, and lets a rescan skip unchanged files without reading
them. The only module that touches catalog.db; does not walk folders or index contents.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from rapidfuzz import fuzz, process, utils

from core.exceptions import IndexingError
from models.schema import CatalogEntry, CatalogMatch, CatalogStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path_key TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    modified_ts REAL NOT NULL,
    status TEXT NOT NULL,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_modified ON files(modified_ts);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
MIN_NAME_MATCH_SCORE = 60.0


def path_key(path: Path | str) -> str:
    """Windows paths are case-insensitive, so the catalog keys on the lowercased path."""
    return str(path).lower()


def folder_prefix(root: Path | str) -> str:
    """The path_key prefix shared by everything inside root. The trailing separator stops
    C:\\Docs from also matching C:\\Docs2."""
    return path_key(root).rstrip("\\/") + "\\"


class FileCatalog:
    """Thread-safe access to catalog.db — the watcher, the index worker and API requests all
    read and write it from different threads."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        # Name search runs on every "find"/"open" message; re-reading 100k+ rows each time
        # would undo the point of an instant fast path. Only writes that change names, sizes or
        # dates bump the generation — status updates during indexing don't.
        self._name_cache: list[tuple] | None = None
        self._names: list[str] = []
        self._generation = 0

    def connect(self) -> None:
        """Opens (creating if needed) the catalog database."""
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.executescript(SCHEMA)
        except (OSError, sqlite3.Error) as e:
            raise IndexingError(f"Couldn't open the file catalog at {self._db_path}: {e}") from e

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def snapshot(self) -> dict[str, CatalogEntry]:
        """Every cataloged file keyed by path_key — loaded once per scan to diff against disk."""
        rows = self._query("SELECT path, size_bytes, modified_ts, status FROM files")
        return {path_key(r[0]): CatalogEntry(Path(r[0]), r[1], r[2], CatalogStatus(r[3])) for r in rows}

    def entry_for(self, path: Path) -> CatalogEntry | None:
        """One file's catalog row, if it has one."""
        rows = self._query(
            "SELECT path, size_bytes, modified_ts, status FROM files WHERE path_key = ?", (path_key(path),)
        )
        return CatalogEntry(Path(rows[0][0]), rows[0][1], rows[0][2], CatalogStatus(rows[0][3])) if rows else None

    def upsert(self, entries: Iterable[CatalogEntry]) -> None:
        """Inserts or replaces entries, clearing any stale error from a previous version."""
        rows = [
            (path_key(e.path), str(e.path), e.path.name, e.size_bytes, e.modified_ts, e.status.value) for e in entries
        ]
        self._execute_many(
            "INSERT OR REPLACE INTO files (path_key, path, name, size_bytes, modified_ts, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        self._invalidate_names()

    def set_status(self, path: Path, status: CatalogStatus, error: str | None = None) -> None:
        """Records the outcome of indexing one file."""
        self._execute_many(
            "UPDATE files SET status = ?, error = ? WHERE path_key = ?", [(status, error, path_key(path))]
        )

    def remove(self, paths: Iterable[Path]) -> None:
        self._execute_many("DELETE FROM files WHERE path_key = ?", [(path_key(p),) for p in paths])
        self._invalidate_names()

    def remove_under(self, root: Path) -> None:
        """Drops every file below root — used when the user removes a source folder."""
        prefix = folder_prefix(root)
        self._execute_many("DELETE FROM files WHERE substr(path_key, 1, ?) = ?", [(len(prefix), prefix)])
        self._invalidate_names()

    def requeue_all(self) -> None:
        """Marks every content file pending again — for a full rebuild or an embedding-model change."""
        self._execute_many(
            "UPDATE files SET status = ?, error = NULL WHERE status IN (?, ?)",
            [(CatalogStatus.PENDING, CatalogStatus.INDEXED, CatalogStatus.FAILED)],
        )

    def pending_files(self) -> list[tuple[Path, float]]:
        """Files still waiting for content indexing, with their mtime for prioritising."""
        rows = self._query("SELECT path, modified_ts FROM files WHERE status = ?", (CatalogStatus.PENDING,))
        return [(Path(r[0]), r[1]) for r in rows]

    def status_counts(self) -> dict[CatalogStatus, int]:
        rows = self._query("SELECT status, COUNT(*) FROM files GROUP BY status")
        return {CatalogStatus(status): count for status, count in rows}

    def count_under(self, root: Path) -> tuple[int, int]:
        """(all files, content-indexed files) below root, for the Settings window's source list."""
        prefix = folder_prefix(root)
        rows = self._query(
            "SELECT COUNT(*), SUM(status = ?) FROM files WHERE substr(path_key, 1, ?) = ?",
            (CatalogStatus.INDEXED, len(prefix), prefix),
        )
        return rows[0][0], rows[0][1] or 0

    def search_names(self, query: str, limit: int = 10) -> list[CatalogMatch]:
        """Fuzzy-matches query against every cataloged file name, best match first."""
        if not query.strip():
            return []
        rows, names = self._name_index()
        if not rows:
            return []
        hits = process.extract(query, names, scorer=fuzz.WRatio, processor=utils.default_process, limit=limit)
        return [_to_match(rows[index], score) for _, score, index in hits if score >= MIN_NAME_MATCH_SCORE]

    def recent_files(self, since: datetime, limit: int = 25) -> list[CatalogMatch]:
        """Files modified at or after since, newest first."""
        rows = self._query(
            "SELECT path, name, size_bytes, modified_ts FROM files WHERE modified_ts >= ? "
            "ORDER BY modified_ts DESC LIMIT ?",
            (since.timestamp(), limit),
        )
        return [_to_match(row, 100.0) for row in rows]

    def get_meta(self, key: str) -> str | None:
        rows = self._query("SELECT value FROM meta WHERE key = ?", (key,))
        return rows[0][0] if rows else None

    def set_meta(self, key: str, value: str) -> None:
        self._execute_many("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", [(key, value)])

    def _name_index(self) -> tuple[list[tuple], list[str]]:
        """The cached (row, name) lists for fuzzy search, rebuilt after a name-changing write."""
        with self._lock:
            if self._name_cache is not None:
                return self._name_cache, self._names
            generation = self._generation
        rows = self._query("SELECT path, name, size_bytes, modified_ts FROM files")
        names = [row[1] for row in rows]
        with self._lock:
            # A write that landed while we were reading means this snapshot is already stale.
            if generation == self._generation:
                self._name_cache, self._names = rows, names
        return rows, names

    def _invalidate_names(self) -> None:
        with self._lock:
            self._generation += 1
            self._name_cache = None

    def _query(self, sql: str, params: tuple[object, ...] = ()) -> list[tuple]:
        """Runs one read under the lock, wrapping driver errors."""
        with self._lock:
            try:
                return self._require_conn().execute(sql, params).fetchall()
            except sqlite3.Error as e:
                raise IndexingError(f"File catalog read failed: {e}") from e

    def _execute_many(self, sql: str, rows: list[tuple]) -> None:
        """Runs one batched write in a single transaction under the lock."""
        if not rows:
            return
        with self._lock:
            conn = self._require_conn()
            try:
                with conn:
                    conn.executemany(sql, rows)
            except sqlite3.Error as e:
                raise IndexingError(f"File catalog write failed: {e}") from e

    def _require_conn(self) -> sqlite3.Connection:
        """Fails loudly if a caller forgot connect()."""
        if self._conn is None:
            raise IndexingError("The file catalog isn't open yet — call connect() first.")
        return self._conn


def _to_match(row: tuple, score: float) -> CatalogMatch:
    """Builds a CatalogMatch from a (path, name, size, mtime) row."""
    path, name, size_bytes, modified_ts = row
    return CatalogMatch(
        file_path=path,
        file_name=name,
        size_bytes=size_bytes,
        modified_at=datetime.fromtimestamp(modified_ts),
        score=float(score),
    )
