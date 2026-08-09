"""
Turns a query string into ranked chunks: embeds the query, then searches the vector store.
Does not call the LLM and does not decide what to do with the results — that's query_engine's job.
"""

from __future__ import annotations

from datetime import datetime

from core.embedder import Embedder
from core.vector_store import VectorStore
from models.schema import SearchResult

DEFAULT_TOP_K = 5


class Retriever:
    """Embeds a query and ranks matching chunks from the vector store."""

    def __init__(self, store: VectorStore, embedder: Embedder) -> None:
        self._store = store
        self._embedder = embedder

    def retrieve(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        file_type: str | None = None,
        modified_after: datetime | None = None,
    ) -> list[SearchResult]:
        """Returns the top_k chunks most relevant to query, optionally filtered by file_type or recency."""
        query_vector = self._embedder.embed([query])[0]
        return self._store.search(query_vector, top_k=top_k, file_type=file_type, modified_after=modified_after)
