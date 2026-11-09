"""
The only module that talks to LanceDB — every read or write of indexed chunks goes through
here. Keeps a vector index for meaning and a full-text index for exact words (names, IDs,
codes). Does not parse, chunk, or embed anything; it just persists and retrieves chunks.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa
from lancedb.index import FTS

from config.settings import get_settings
from core.exceptions import IndexingError, QueryError
from core.logger import get_logger
from models.schema import IndexedChunk, SearchResult

logger = get_logger(__name__)

TABLE_NAME = "chunks"
META_FILE_NAME = "index_meta.json"
# Bump when the row layout changes; a mismatch (or a different embedding model) triggers a
# clean rebuild instead of mixing incompatible vectors in one table.
SCHEMA_VERSION = 2
DELETE_BATCH_SIZE = 200


class VectorStore:
    """A LanceDB table of IndexedChunk rows, with vector and full-text search."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or get_settings().lancedb_path
        self._db: lancedb.DBConnection | None = None
        self._table: lancedb.table.Table | None = None
        # LanceDB tables aren't safe for concurrent writers; reads stay lock-free.
        self._write_lock = threading.Lock()

    def connect(self) -> None:
        """Opens the LanceDB database, picking up the chunks table if one already exists."""
        try:
            self._db_path.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(str(self._db_path))
            if TABLE_NAME in self._db.list_tables().tables:
                self._table = self._db.open_table(TABLE_NAME)
        except Exception as e:
            raise IndexingError(f"Couldn't open the LanceDB store at {self._db_path}: {e}") from e

    def ensure_compatible(self, embedding_model: str) -> bool:
        """Drops the table if it was built by another embedding model or row layout. Returns
        True when it did, so the caller knows every file needs re-indexing."""
        expected = {"schema_version": SCHEMA_VERSION, "embedding_model": embedding_model}
        meta_path = self._db_path / META_FILE_NAME
        current = _read_meta(meta_path)
        # A table with no meta file predates versioning, so it's incompatible too.
        was_reset = (current is not None and current != expected) or (current is None and self._table is not None)
        if was_reset:
            logger.warning("Index was built differently, rebuilding", extra={"found": current, "expected": expected})
            self.drop_all()
        meta_path.write_text(json.dumps(expected), encoding="utf-8")
        return was_reset

    def upsert_chunks(self, chunks: list[IndexedChunk]) -> None:
        """Replaces every row for each chunk's file with the new set — a changed file's chunk
        boundaries can shift, so a partial merge would leave stale rows behind."""
        if not chunks:
            return
        rows = [c.model_dump() for c in chunks]
        with self._write_lock:
            try:
                if self._table is None:
                    self._create_table(rows, vector_dim=len(chunks[0].vector))
                    return
                for path in {c.file_path for c in chunks}:
                    self._table.delete(_path_filter(path))
                self._table.add(rows)
            except Exception as e:
                raise IndexingError(f"Failed to write {len(chunks)} chunk(s) to the vector store: {e}") from e

    def search(
        self, query_vector: list[float], top_k: int = 5, modified_after: datetime | None = None
    ) -> list[SearchResult]:
        """The top_k chunks nearest in meaning to query_vector, optionally only recent ones."""
        if self._table is None:
            return []
        try:
            query = self._table.search(query_vector).limit(top_k)
            if modified_after is not None:
                query = query.where(f"modified_at >= timestamp '{modified_after.isoformat()}'", prefilter=True)
            rows = query.to_list()
        except Exception as e:
            raise QueryError(f"Vector search failed: {e}") from e
        # Distance is lower-is-better; every SearchResult score in Nimbus is higher-is-better.
        return [_row_to_search_result(row, score=1.0 / (1.0 + float(row.get("_distance", 0.0)))) for row in rows]

    def search_text(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """The top_k chunks matching query's exact words. Returns [] for a query the full-text
        parser can't handle — keyword search is a bonus signal, never the only one."""
        if self._table is None or not query.strip():
            return []
        try:
            rows = self._table.search(query, query_type="fts").limit(top_k).to_list()
        except Exception as e:
            logger.info("Full-text search skipped", extra={"error": str(e)})
            return []
        return [_row_to_search_result(row, score=float(row.get("_score", 0.0))) for row in rows]

    def content_hash_for(self, file_path: str) -> str | None:
        """The content hash stored for file_path, or None if it has no rows."""
        if self._table is None:
            return None
        try:
            rows = self._table.search().where(_path_filter(file_path)).select(["content_hash"]).limit(1).to_list()
        except Exception as e:
            raise IndexingError(f"Hash lookup failed for {file_path}: {e}") from e
        return rows[0]["content_hash"] if rows else None

    def delete_by_path(self, file_path: str) -> None:
        """Removes every chunk belonging to file_path."""
        self._delete(_path_filter(file_path), file_path)

    def delete_by_paths(self, file_paths: list[str]) -> None:
        """Removes every chunk of several files, in batches so one filter string stays small."""
        for start in range(0, len(file_paths), DELETE_BATCH_SIZE):
            batch = file_paths[start : start + DELETE_BATCH_SIZE]
            quoted = ", ".join(f"'{_escape_sql(p)}'" for p in batch)
            self._delete(f"file_path IN ({quoted})", f"{len(batch)} file(s)")

    def delete_under(self, root: Path) -> None:
        """Removes every chunk of every file below root — for a removed source folder."""
        prefix = str(root).rstrip("\\/").lower() + "\\"
        self._delete(f"starts_with(lower(file_path), '{_escape_sql(prefix)}')", str(root))

    def drop_all(self) -> None:
        """Deletes the whole table — the next upsert recreates it."""
        with self._write_lock:
            if self._table is not None:
                self._db.drop_table(TABLE_NAME)
                self._table = None

    def optimize(self) -> None:
        """Folds recently added rows into the full-text index and compacts deleted ones.
        Cheap to skip, so failures are logged rather than raised."""
        if self._table is None:
            return
        with self._write_lock:
            try:
                self._table.optimize()
            except Exception as e:
                logger.warning("Index optimize failed", extra={"error": str(e)})

    def count(self) -> int:
        """Total number of indexed chunks."""
        return self._table.count_rows() if self._table is not None else 0

    def _create_table(self, rows: list[dict[str, Any]], vector_dim: int) -> None:
        """Creates the table from its first rows, plus the full-text index over chunk text."""
        self._table = self._db.create_table(TABLE_NAME, data=rows, schema=_build_schema(vector_dim))
        self._table.create_index("chunk_text", config=FTS(), replace=True)

    def _delete(self, where: str, label: str) -> None:
        """Runs one delete under the write lock."""
        if self._table is None:
            return
        with self._write_lock:
            try:
                self._table.delete(where)
            except Exception as e:
                raise IndexingError(f"Failed to delete rows for {label}: {e}") from e


def _read_meta(meta_path: Path) -> dict[str, Any] | None:
    """The stored index metadata. An unreadable file counts as "built differently", which
    triggers a clean rebuild instead of refusing to start."""
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Index metadata unreadable, rebuilding", extra={"path": str(meta_path)})
        return {"unreadable": True}


def _build_schema(vector_dim: int) -> pa.Schema:
    """Fixes the vector column to vector_dim so LanceDB can build an ANN index over it."""
    return pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("file_path", pa.string()),
            pa.field("file_name", pa.string()),
            pa.field("file_type", pa.string()),
            pa.field("content_hash", pa.string()),
            pa.field("chunk_index", pa.int64()),
            pa.field("chunk_text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), vector_dim)),
            pa.field("created_at", pa.timestamp("us")),
            pa.field("modified_at", pa.timestamp("us")),
            pa.field("indexed_at", pa.timestamp("us")),
        ]
    )


def _row_to_search_result(row: dict[str, Any], score: float) -> SearchResult:
    """Converts a raw LanceDB hit into a SearchResult carrying the given raw score."""
    return SearchResult(
        chunk_id=row["id"],
        chunk_text=row["chunk_text"],
        file_path=row["file_path"],
        file_name=row["file_name"],
        score=score,
        metadata={
            "file_type": row["file_type"],
            "chunk_index": row["chunk_index"],
            "modified_at": row["modified_at"],
        },
    )


def _path_filter(file_path: str) -> str:
    return f"file_path = '{_escape_sql(file_path)}'"


def _escape_sql(value: str) -> str:
    """Doubles single quotes so a path containing one can't break a LanceDB filter string."""
    return value.replace("'", "''")
