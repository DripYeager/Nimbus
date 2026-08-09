"""
The only module that talks to LanceDB — every read or write to the index goes through here.
Does not parse, chunk, or embed anything; it just persists and retrieves IndexedChunk rows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa

from config.settings import get_settings
from core.exceptions import IndexingError, QueryError
from models.schema import IndexedChunk, SearchResult

TABLE_NAME = "chunks"


class VectorStore:
    """A LanceDB table of IndexedChunk rows."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or get_settings().lancedb_path
        self._db: lancedb.DBConnection | None = None
        self._table: lancedb.table.Table | None = None

    def connect(self) -> None:
        """Opens the LanceDB database, picking up the chunks table if one already exists."""
        try:
            self._db_path.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(str(self._db_path))
        except Exception as e:
            raise IndexingError(f"Couldn't open the LanceDB store at {self._db_path}: {e}") from e
        if TABLE_NAME in self._db.list_tables().tables:
            self._table = self._db.open_table(TABLE_NAME)

    def upsert_chunks(self, chunks: list[IndexedChunk]) -> None:
        """Drops any existing rows for each chunk's file, then inserts the new set — a changed
        file's chunk boundaries can shift, so a partial merge would leave stale rows behind."""
        if not chunks:
            return
        rows = [_chunk_to_row(c) for c in chunks]
        try:
            if self._table is None:
                schema = _build_schema(len(chunks[0].vector))
                self._table = self._db.create_table(TABLE_NAME, data=rows, schema=schema)
                return
            for path in {c.file_path for c in chunks}:
                self._table.delete(f"file_path = '{_escape_sql(path)}'")
            self._table.add(rows)
        except Exception as e:
            raise IndexingError(f"Failed to write {len(chunks)} chunk(s) to the vector store: {e}") from e

    def search(self, query_vector: list[float], top_k: int = 5, file_type: str | None = None) -> list[SearchResult]:
        """Returns the top_k chunks nearest to query_vector, optionally restricted to one file_type."""
        if self._table is None:
            return []
        try:
            query = self._table.search(query_vector).limit(top_k)
            if file_type is not None:
                query = query.where(f"file_type = '{_escape_sql(file_type)}'")
            rows = query.to_list()
        except Exception as e:
            raise QueryError(f"Vector search failed: {e}") from e
        return [_row_to_search_result(row) for row in rows]

    def delete_by_path(self, file_path: str) -> None:
        """Removes every chunk belonging to file_path — used when the watcher sees a delete or move."""
        if self._table is None:
            return
        try:
            self._table.delete(f"file_path = '{_escape_sql(file_path)}'")
        except Exception as e:
            raise IndexingError(f"Failed to delete rows for {file_path}: {e}") from e

    def get_by_hash(self, content_hash: str) -> IndexedChunk | None:
        """Looks up one chunk by its file's content hash — the incremental-skip check."""
        if self._table is None:
            return None
        try:
            rows = self._table.search().where(f"content_hash = '{_escape_sql(content_hash)}'").limit(1).to_list()
        except Exception as e:
            raise IndexingError(f"Hash lookup failed for {content_hash}: {e}") from e
        return _row_to_chunk(rows[0]) if rows else None

    def count(self) -> int:
        """Total number of indexed chunks."""
        return self._table.count_rows() if self._table is not None else 0


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


def _chunk_to_row(chunk: IndexedChunk) -> dict[str, Any]:
    """One-line, but named so upsert_chunks doesn't have to know IndexedChunk's field layout."""
    return chunk.model_dump()


def _row_to_chunk(row: dict[str, Any]) -> IndexedChunk:
    """Rebuilds an IndexedChunk from a raw LanceDB row."""
    return IndexedChunk(
        id=row["id"],
        file_path=row["file_path"],
        file_name=row["file_name"],
        file_type=row["file_type"],
        content_hash=row["content_hash"],
        chunk_index=row["chunk_index"],
        chunk_text=row["chunk_text"],
        vector=list(row["vector"]),
        created_at=row["created_at"],
        modified_at=row["modified_at"],
        indexed_at=row["indexed_at"],
    )


def _row_to_search_result(row: dict[str, Any]) -> SearchResult:
    """Converts a raw LanceDB search hit into a SearchResult."""
    return SearchResult(
        chunk_text=row["chunk_text"],
        file_path=row["file_path"],
        file_name=row["file_name"],
        score=float(row.get("_distance", 0.0)),
        metadata={"file_type": row["file_type"], "chunk_index": row["chunk_index"]},
    )


def _escape_sql(value: str) -> str:
    """Doubles single quotes so a path or hash containing one can't break a LanceDB filter string."""
    return value.replace("'", "''")
