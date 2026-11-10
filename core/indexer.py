"""
Indexes one file's contents: hash -> parse (OCR if needed) -> chunk -> embed -> store.
Does not decide which files to index or when, the index service owns that, and does not
parse, chunk, or embed itself; it only calls the modules that do, in order.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from config.settings import get_settings
from core.document_parser import extract_document_pages
from core.embedder import Embedder
from core.exceptions import IndexingError
from core.logger import get_logger
from core.text_chunker import chunk_text
from core.vector_store import VectorStore
from models.schema import DocumentPage, IndexedChunk

logger = get_logger(__name__)

HASH_BLOCK_BYTES = 1024 * 1024


class Indexer:
    """Turns one file into embedded, searchable chunks in the vector store."""

    def __init__(self, store: VectorStore, embedder: Embedder) -> None:
        self._store = store
        self._embedder = embedder

    def index_file(self, path: Path) -> int:
        """(Re)indexes path, replacing any rows it had before. Returns the chunks written,
        0 when the contents are unchanged or no text could be extracted."""
        settings = get_settings()
        content_hash = hash_file(path)
        if self._store.content_hash_for(str(path)) == content_hash:
            # Saving without changes, or a sync client touching mtime, shouldn't cost a re-embed.
            logger.info("Contents unchanged, skipping", extra={"path": str(path)})
            return 0
        pages = extract_document_pages(path)
        chunks = _chunk_pages(pages, settings.max_chunk_size, settings.chunk_overlap)
        if not chunks:
            self._store.delete_by_path(str(path))
            logger.info("No text extracted, nothing to index", extra={"path": str(path)})
            return 0
        vectors = self._embedder.embed([text for _, text in chunks])
        self._store.upsert_chunks(_build_indexed_chunks(path, content_hash, chunks, vectors))
        logger.info("Indexed file", extra={"path": str(path), "chunks": len(chunks)})
        return len(chunks)

    def optimize_store(self) -> None:
        """Lets the store fold freshly written rows into its search indexes."""
        self._store.optimize()


def hash_file(path: Path) -> str:
    """MD5 of the file's bytes, read in 1 MB blocks so a multi-GB file never sits in memory."""
    digest = hashlib.md5()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(HASH_BLOCK_BYTES), b""):
                digest.update(block)
    except OSError as e:
        raise IndexingError(f"Couldn't read {path} to hash it: {e}") from e
    return digest.hexdigest()


def _chunk_pages(pages: list[DocumentPage], chunk_size: int, overlap: int) -> list[tuple[int | None, str]]:
    """(page number, chunk text) pairs. Each page is chunked on its own, so a chunk never spans
    two pages and every answer can cite exactly one."""
    return [
        (page.number, chunk)
        for page in pages
        for chunk in chunk_text(page.text, chunk_size=chunk_size, overlap=overlap)
    ]


def _build_indexed_chunks(
    path: Path, content_hash: str, chunks: list[tuple[int | None, str]], vectors: list[list[float]]
) -> list[IndexedChunk]:
    """Pairs each chunk with its vector and the file metadata they all share."""
    now = datetime.now()
    stat = path.stat()
    return [
        IndexedChunk(
            id=str(uuid4()),
            file_path=str(path),
            file_name=path.name,
            file_type=path.suffix.lstrip(".").lower(),
            content_hash=content_hash,
            chunk_index=i,
            chunk_text=chunk,
            page=page,
            vector=vector,
            created_at=datetime.fromtimestamp(stat.st_ctime),
            modified_at=datetime.fromtimestamp(stat.st_mtime),
            indexed_at=now,
        )
        for i, ((page, chunk), vector) in enumerate(zip(chunks, vectors, strict=True))
    ]
