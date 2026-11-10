"""
The SQL behind the search index: the table layout and the search queries. Statements only,
core/vector_store.py runs them.
"""

from __future__ import annotations

SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    rowid INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    path_key TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    page INTEGER,
    created_at REAL NOT NULL,
    modified_at REAL NOT NULL,
    indexed_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path_key);
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(chunk_text, tokenize='porter unicode61');
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
# The embedding size is only known once the first chunk arrives, so this table is created then.
VECTOR_TABLE = (
    "CREATE VIRTUAL TABLE chunk_vectors USING vec0(embedding float[{dim}] distance_metric=cosine, modified_at float)"
)
CHUNK_COLUMNS = "c.id, c.file_path, c.file_name, c.file_type, c.chunk_index, c.chunk_text, c.modified_at, c.page"
SEARCH_SQL = (
    "WITH knn AS (SELECT rowid, distance FROM chunk_vectors WHERE embedding MATCH ? AND k = ?{recency}) "
    f"SELECT {CHUNK_COLUMNS}, knn.distance FROM knn JOIN chunks c ON c.rowid = knn.rowid ORDER BY knn.distance"
)
TEXT_SEARCH_SQL = (
    f"SELECT {CHUNK_COLUMNS}, bm25(chunk_fts) FROM chunk_fts JOIN chunks c ON c.rowid = chunk_fts.rowid "
    "WHERE chunk_fts MATCH ? ORDER BY bm25(chunk_fts) LIMIT ?"
)
VECTOR_TABLE_EXISTS_SQL = "SELECT 1 FROM sqlite_master WHERE name = 'chunk_vectors'"
