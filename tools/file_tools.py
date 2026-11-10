"""
Read-only file lookups: rank indexed files by relevance to a query, and read a file's size and
timestamps from disk. Owns these lookups only; no LLM calls, no writes, and no decisions about
which folders are allowed (callers check that first).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from core.exceptions import QueryError
from core.retriever import Retriever
from models.schema import CatalogMatch, FileMetadata, SearchResult, SourceRef

DEFAULT_FILE_RESULTS = 5
# Several top chunks can come from the same file, so we oversample chunks before deduplicating
# down to distinct files, otherwise a single dominant file could crowd out the top_k file count.
CHUNK_OVERSAMPLE_FACTOR = 4


def find_files(retriever: Retriever, query: str, top_k: int = DEFAULT_FILE_RESULTS) -> list[SourceRef]:
    """Finds the top_k files whose contents best match query, one entry per file, best first."""
    chunks = retriever.retrieve(query, top_k=top_k * CHUNK_OVERSAMPLE_FACTOR)
    return rank_unique_files(chunks)[:top_k]


def rank_unique_files(chunks: list[SearchResult]) -> list[SourceRef]:
    """Deduplicates chunks down to one entry per file, ranked by relevance (highest score first)."""
    best_per_file = _best_chunk_per_file(chunks)
    ranked = sorted(best_per_file.values(), key=lambda chunk: chunk.score, reverse=True)
    return [SourceRef(file_name=c.file_name, file_path=c.file_path, score=c.score, page=c.page) for c in ranked]


def page_label(page: int | None) -> str:
    """ " (p. 12)" for a known page, so answers can cite it; nothing otherwise."""
    return f" (p. {page})" if page is not None else ""


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


def source_ref_for(path: Path) -> SourceRef:
    """A clickable source for a file a tool touched directly, rather than found by search."""
    return SourceRef(file_name=path.name, file_path=str(path), score=1.0)


def source_ref_for_match(match: CatalogMatch) -> SourceRef:
    """A clickable source for a file found by name in the catalog."""
    return SourceRef(file_name=match.file_name, file_path=match.file_path, score=match.score)


def _best_chunk_per_file(chunks: list[SearchResult]) -> dict[str, SearchResult]:
    """Keeps only the highest-scoring chunk seen for each file_path."""
    best_per_file: dict[str, SearchResult] = {}
    for chunk in chunks:
        current_best = best_per_file.get(chunk.file_path)
        if current_best is None or chunk.score > current_best.score:
            best_per_file[chunk.file_path] = chunk
    return best_per_file
