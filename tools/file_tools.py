"""
Serves FILE_SEARCH and METADATA: find_files ranks indexed files by relevance, get_metadata
and list_recent are plain filesystem lookups. Owns these three lookups. Does not call the LLM.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from core.exceptions import QueryError
from core.retriever import Retriever
from models.schema import FileMetadata, SearchResult, SourceRef

DEFAULT_FILE_RESULTS = 5
DEFAULT_LIST_LIMIT = 50
# Several top chunks can come from the same file, so we oversample chunks before deduplicating
# down to distinct files — otherwise a single dominant file could crowd out the top_k file count.
CHUNK_OVERSAMPLE_FACTOR = 4


def find_files(retriever: Retriever, query: str, top_k: int = DEFAULT_FILE_RESULTS) -> list[SourceRef]:
    """Finds the top_k files most relevant to query, one entry per file, best match first."""
    chunks = retriever.retrieve(query, top_k=top_k * CHUNK_OVERSAMPLE_FACTOR)
    return rank_unique_files(chunks)[:top_k]


def rank_unique_files(chunks: list[SearchResult]) -> list[SourceRef]:
    """Deduplicates chunks down to one entry per file, ranked by relevance (lowest distance first)."""
    best_per_file = _best_chunk_per_file(chunks)
    ranked = sorted(best_per_file.values(), key=lambda chunk: chunk.score)
    return [SourceRef(file_name=c.file_name, file_path=c.file_path, score=c.score) for c in ranked]


def get_metadata(path: Path) -> FileMetadata | None:
    """Reads a file's size and timestamps from the filesystem. Returns None if it doesn't exist."""
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise QueryError(f"Couldn't read metadata for {path}: {e}") from e
    return FileMetadata(
        file_path=str(path),
        file_name=path.name,
        size_bytes=stat.st_size,
        created_at=datetime.fromtimestamp(stat.st_ctime),
        modified_at=datetime.fromtimestamp(stat.st_mtime),
    )


def list_recent(directory: Path, modified_after: datetime, limit: int = DEFAULT_LIST_LIMIT) -> list[FileMetadata]:
    """Lists files directly inside directory modified after modified_after, most recent first."""
    try:
        entries = [p for p in directory.iterdir() if p.is_file()]
    except OSError as e:
        raise QueryError(f"Couldn't list files in {directory}: {e}") from e

    matches = [m for m in (get_metadata(p) for p in entries) if m is not None and m.modified_at >= modified_after]
    matches.sort(key=lambda m: m.modified_at, reverse=True)
    return matches[:limit]


def _best_chunk_per_file(chunks: list[SearchResult]) -> dict[str, SearchResult]:
    """Keeps only the lowest-distance (most relevant) chunk seen so far for each file_path."""
    best_per_file: dict[str, SearchResult] = {}
    for chunk in chunks:
        current_best = best_per_file.get(chunk.file_path)
        if current_best is None or chunk.score < current_best.score:
            best_per_file[chunk.file_path] = chunk
    return best_per_file
