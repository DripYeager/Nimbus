"""
Splits text into overlapping word-count windows for embedding.
Pure function, no I/O — does not read files and does not know about the vector store.
"""

from __future__ import annotations

DEFAULT_CHUNK_SIZE = 512
DEFAULT_OVERLAP = 50


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP) -> list[str]:
    """Splits text into chunk_size-word windows, each overlapping the next by overlap words."""
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(f"overlap must be >= 0 and < chunk_size, got overlap={overlap}, chunk_size={chunk_size}")

    words = text.split()
    if not words:
        return []

    step = chunk_size - overlap
    chunks = []
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start : start + chunk_size]))
        if start + chunk_size >= len(words):
            break
    return chunks
