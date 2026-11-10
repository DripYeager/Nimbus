"""
The only module that touches the search index, every read or write of indexed chunks goes
through here. One SQLite file holds the chunk rows, their embeddings (a sqlite-vec table, for
meaning) and an FTS5 full-text table (for exact words like names, IDs and codes). Does not
parse, chunk or embed anything; it just persists and retrieves chunks.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import sqlite_vec

from config.settings import get_settings
from core.exceptions import IndexingError, QueryError
from core.file_catalog import folder_prefix, path_key
from core.logger import get_logger
from core.search_query import build_fts_query
from core.vector_store_sql import (
    SCHEMA,
    SEARCH_SQL,
    TEXT_SEARCH_SQL,
    VECTOR_TABLE,
    VECTOR_TABLE_EXISTS_SQL,
)
from models.schema import IndexedChunk, SearchResult

logger = get_logger(__name__)

# Bump when the layout changes; a mismatch (or a different embedding model) triggers a clean
# rebuild instead of mixing incompatible vectors.
SCHEMA_VERSION = "4"
DELETE_BATCH_SIZE = 200
READER_MMAP_BYTES = 256 * 1024 * 1024
READER_CACHE_KIB = 64 * 1024


class VectorStore:
    """Chunks with vector and full-text search, in one SQLite file. A writer and a reader
    connection in WAL mode let searches run while the index worker is writing."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or get_settings().search_index_path
        self._writer: sqlite3.Connection | None = None
        self._reader: sqlite3.Connection | None = None
        self._write_lock = threading.Lock()
        self._read_lock = threading.Lock()

    def connect(self) -> None:
        """Opens (creating if needed) the index file."""
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._writer = _open(self._db_path)
            self._writer.execute("PRAGMA journal_mode=WAL")
            self._writer.executescript(SCHEMA)
            self._reader = _open(self._db_path)
            # Vector search scans every embedding (~1.5 KB each). With SQLite's default 2 MB page
            # cache each search re-reads them from disk; memory-mapping the file and a larger
            # cache make a 20k-chunk search about 3.5x faster.
            self._reader.execute(f"PRAGMA mmap_size = {READER_MMAP_BYTES}")
            self._reader.execute(f"PRAGMA cache_size = -{READER_CACHE_KIB}")
        except (OSError, sqlite3.Error) as e:
            raise IndexingError(f"Couldn't open the search index at {self._db_path}: {e}") from e

    def close(self) -> None:
        """Closes both connections. Safe to call twice."""
        for conn in (self._writer, self._reader):
            if conn is not None:
                conn.close()
        self._writer = self._reader = None

    def ensure_compatible(self, embedding_model: str) -> bool:
        """Clears the index if it was built by another embedding model or layout. Returns True
        when it did, so the caller knows every file needs re-indexing."""
        expected = {"schema_version": SCHEMA_VERSION, "embedding_model": embedding_model}
        current = dict(self._read("SELECT key, value FROM meta"))
        # Chunks with no metadata predate versioning, so they're incompatible too.
        was_reset = current != expected and (bool(current) or self.count() > 0)
        if was_reset:
            logger.warning("Index was built differently, rebuilding", extra={"found": current, "expected": expected})
            self.drop_all()
        with self._transaction() as conn:
            conn.executemany("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", expected.items())
        return was_reset

    def upsert_chunks(self, chunks: list[IndexedChunk]) -> None:
        """Replaces every row for each chunk's file with the new set, a changed file's chunk
        boundaries can shift, so a partial merge would leave stale rows behind."""
        if not chunks:
            return
        try:
            with self._transaction() as conn:
                _ensure_vector_table(conn, len(chunks[0].vector))
                for key in {path_key(c.file_path) for c in chunks}:
                    _delete_where(conn, "path_key = ?", (key,))
                for chunk in chunks:
                    _insert_chunk(conn, chunk)
        except sqlite3.Error as e:
            raise IndexingError(f"Failed to write {len(chunks)} chunk(s) to the search index: {e}") from e

    def search(
        self, query_vector: list[float], top_k: int = 5, modified_after: datetime | None = None
    ) -> list[SearchResult]:
        """The top_k chunks nearest in meaning to query_vector, optionally only recent ones."""
        params: list[Any] = [sqlite_vec.serialize_float32(query_vector), top_k]
        recency = ""
        if modified_after is not None:
            recency, params = " AND modified_at >= ?", [*params, modified_after.timestamp()]
        try:
            if not self._has_vectors():
                return []
            rows = self._read(SEARCH_SQL.format(recency=recency), tuple(params))
        except IndexingError as e:
            raise QueryError(f"Vector search failed: {e}") from e
        # Cosine distance is lower-is-better; every SearchResult score in Nimbus is higher-is-better.
        return [_to_result(row, score=1.0 / (1.0 + row[-1])) for row in rows]

    def search_text(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """The top_k chunks containing query's meaningful words, best BM25 match first. Each word
        is matched as a phrase, so "INV-2231" finds that exact code rather than any "INV"."""
        fts_query = build_fts_query(query)
        if fts_query is None:
            return []
        try:
            rows = self._read(TEXT_SEARCH_SQL, (fts_query, top_k))
        except IndexingError as e:
            logger.info("Full-text search skipped", extra={"error": str(e)})
            return []
        return [_to_result(row, score=-row[-1]) for row in rows]

    def content_hash_for(self, file_path: str) -> str | None:
        """The content hash stored for file_path, or None if it has no rows."""
        rows = self._read("SELECT content_hash FROM chunks WHERE path_key = ? LIMIT 1", (path_key(file_path),))
        return rows[0][0] if rows else None

    def delete_by_path(self, file_path: str) -> None:
        """Removes every chunk belonging to file_path."""
        self._delete("path_key = ?", (path_key(file_path),), file_path)

    def delete_by_paths(self, file_paths: list[str]) -> None:
        """Removes every chunk of several files, in batches to stay under SQLite's parameter limit."""
        for start in range(0, len(file_paths), DELETE_BATCH_SIZE):
            keys = [path_key(p) for p in file_paths[start : start + DELETE_BATCH_SIZE]]
            self._delete(f"path_key IN ({', '.join('?' * len(keys))})", tuple(keys), f"{len(keys)} file(s)")

    def delete_under(self, root: Path) -> None:
        """Removes every chunk of every file below root, for a removed source folder."""
        prefix = folder_prefix(root)
        self._delete("substr(path_key, 1, ?) = ?", (len(prefix), prefix), str(root))

    def drop_all(self) -> None:
        """Empties the index; the next upsert recreates the vector table."""
        with self._transaction() as conn:
            conn.execute("DROP TABLE IF EXISTS chunk_vectors")
            conn.execute("DELETE FROM chunk_fts")
            conn.execute("DELETE FROM chunks")

    def optimize(self) -> None:
        """Merges the full-text index's segments. Cheap to skip, so failures are only logged."""
        try:
            with self._transaction() as conn:
                conn.execute("INSERT INTO chunk_fts(chunk_fts) VALUES ('optimize')")
        except (sqlite3.Error, IndexingError) as e:
            logger.warning("Index optimize failed", extra={"error": str(e)})

    def count(self) -> int:
        """Total number of indexed chunks."""
        return self._read("SELECT COUNT(*) FROM chunks")[0][0]

    def _has_vectors(self) -> bool:
        return bool(self._read(VECTOR_TABLE_EXISTS_SQL))

    def _delete(self, where: str, params: tuple[Any, ...], label: str) -> None:
        try:
            with self._transaction() as conn:
                _delete_where(conn, where, params)
        except sqlite3.Error as e:
            raise IndexingError(f"Failed to delete rows for {label}: {e}") from e

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """The writer connection inside one transaction, under the write lock."""
        if self._writer is None:
            raise IndexingError("The search index isn't open yet. Call connect() first.")
        with self._write_lock, self._writer:
            yield self._writer

    def _read(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple]:
        """Runs one read on the reader connection."""
        if self._reader is None:
            raise IndexingError("The search index isn't open yet. Call connect() first.")
        with self._read_lock:
            try:
                return self._reader.execute(sql, params).fetchall()
            except sqlite3.Error as e:
                raise IndexingError(f"Search index read failed: {e}") from e


def _open(db_path: Path) -> sqlite3.Connection:
    """A connection with the sqlite-vec extension loaded."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _has_vector_table(conn: sqlite3.Connection) -> bool:
    return conn.execute(VECTOR_TABLE_EXISTS_SQL).fetchone() is not None


def _ensure_vector_table(conn: sqlite3.Connection, dim: int) -> None:
    if not _has_vector_table(conn):
        conn.execute(VECTOR_TABLE.format(dim=dim))


def _insert_chunk(conn: sqlite3.Connection, chunk: IndexedChunk) -> None:
    """Writes one chunk's row, its embedding and its full-text entry under one rowid."""
    rowid = conn.execute(
        "INSERT INTO chunks (id, file_path, path_key, file_name, file_type, content_hash, chunk_index, "
        "chunk_text, page, created_at, modified_at, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            chunk.id,
            chunk.file_path,
            path_key(chunk.file_path),
            chunk.file_name,
            chunk.file_type,
            chunk.content_hash,
            chunk.chunk_index,
            chunk.chunk_text,
            chunk.page,
            chunk.created_at.timestamp(),
            chunk.modified_at.timestamp(),
            chunk.indexed_at.timestamp(),
        ),
    ).lastrowid
    conn.execute(
        "INSERT INTO chunk_vectors (rowid, embedding, modified_at) VALUES (?, ?, ?)",
        (rowid, sqlite_vec.serialize_float32(chunk.vector), chunk.modified_at.timestamp()),
    )
    conn.execute("INSERT INTO chunk_fts (rowid, chunk_text) VALUES (?, ?)", (rowid, chunk.chunk_text))


def _delete_where(conn: sqlite3.Connection, where: str, params: tuple[Any, ...]) -> None:
    """Deletes matching chunks from all three tables, which share rowids."""
    matching = f"SELECT rowid FROM chunks WHERE {where}"
    if _has_vector_table(conn):
        conn.execute(f"DELETE FROM chunk_vectors WHERE rowid IN ({matching})", params)
    conn.execute(f"DELETE FROM chunk_fts WHERE rowid IN ({matching})", params)
    conn.execute(f"DELETE FROM chunks WHERE {where}", params)


def _to_result(row: tuple, score: float) -> SearchResult:
    """Converts a (CHUNK_COLUMNS..., raw score) row into a SearchResult."""
    chunk_id, file_path, file_name, file_type, chunk_index, chunk_text, modified_at, page = row[:8]
    return SearchResult(
        chunk_id=chunk_id,
        chunk_text=chunk_text,
        file_path=file_path,
        file_name=file_name,
        score=score,
        page=page,
        metadata={
            "file_type": file_type,
            "chunk_index": chunk_index,
            "modified_at": datetime.fromtimestamp(modified_at),
        },
    )
