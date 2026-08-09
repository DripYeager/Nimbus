"""
Wires the indexing pipeline together: hash -> parse -> OCR if needed -> chunk -> embed -> store.
Does not parse, chunk, or embed itself — it only calls the modules that do, in order.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from config.settings import get_settings
from core.document_parser import extract_document_text
from core.embedder import Embedder
from core.exceptions import IndexingError, NimbusError, UnsupportedFileTypeError
from core.logger import get_logger
from core.text_chunker import chunk_text
from core.vector_store import VectorStore
from models.schema import IndexedChunk

logger = get_logger(__name__)


class Indexer:
    """Turns one file into embedded, searchable chunks in the vector store."""

    def __init__(self, store: VectorStore, embedder: Embedder) -> None:
        settings = get_settings()
        self._store = store
        self._embedder = embedder
        self._chunk_size = settings.max_chunk_size
        self._chunk_overlap = settings.chunk_overlap

    def index_file(self, path: Path) -> int:
        """Indexes one file, skipping it if unchanged since last time. Returns chunks written."""
        content_hash = _hash_file(path)
        if self._store.get_by_hash(content_hash) is not None:
            logger.info("Skipping unchanged file", extra={"path": str(path)})
            return 0

        text = extract_document_text(path)
        chunks = chunk_text(text, chunk_size=self._chunk_size, overlap=self._chunk_overlap)
        if not chunks:
            logger.warning("No text extracted, nothing to index", extra={"path": str(path)})
            return 0

        vectors = self._embedder.embed(chunks)
        self._store.upsert_chunks(_build_indexed_chunks(path, content_hash, chunks, vectors))
        logger.info("Indexed file", extra={"path": str(path), "chunks": len(chunks)})
        return len(chunks)

    def index_directory(self, root: Path) -> int:
        """Indexes every file under root, skipping any that fail. Returns the total chunks written."""
        total = 0
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            try:
                total += self.index_file(path)
            except UnsupportedFileTypeError as e:
                logger.info("Skipping file with no available converter", extra={"path": str(path), "error": str(e)})
            except NimbusError as e:
                logger.error("Skipping file that failed to index", extra={"path": str(path), "error": str(e)})
        return total


def _hash_file(path: Path) -> str:
    """MD5 of the file's bytes — cheap enough to run on every watcher event."""
    try:
        return hashlib.md5(path.read_bytes()).hexdigest()
    except OSError as e:
        raise IndexingError(f"Couldn't read {path} to hash it: {e}") from e


def _build_indexed_chunks(
    path: Path, content_hash: str, chunks: list[str], vectors: list[list[float]]
) -> list[IndexedChunk]:
    """Pairs each chunk with its vector and the file metadata they all share."""
    now = datetime.now()
    stat = path.stat()
    return [
        IndexedChunk(
            id=str(uuid4()),
            file_path=str(path),
            file_name=path.name,
            file_type=path.suffix.lstrip("."),
            content_hash=content_hash,
            chunk_index=i,
            chunk_text=chunk,
            vector=vector,
            created_at=datetime.fromtimestamp(stat.st_ctime),
            modified_at=datetime.fromtimestamp(stat.st_mtime),
            indexed_at=now,
        )
        for i, (chunk, vector) in enumerate(zip(chunks, vectors))
    ]
