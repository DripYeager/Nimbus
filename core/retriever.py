"""
Finds the chunks most relevant to a query by fusing two rankings: vector search (meaning) and
full-text search (exact words like "INV-2231" or a person's name), the keyword side counting
only when the question asks for something exact, then, when the optional reranker is ready,
re-scoring the best of them with a cross-encoder. Owns relevance only; does
not call the LLM or decide what to do with the results.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from core.embedder import Embedder
from core.reranker import Reranker
from core.search_query import keyword_weight
from core.vector_store import VectorStore
from models.schema import SearchResult

DEFAULT_TOP_K = 5
# Each ranking is oversampled before fusing, so a chunk that's 7th in both lists can still
# beat one that's 1st in only one of them.
CANDIDATE_MULTIPLIER = 3
# The standard reciprocal-rank-fusion damping constant: large enough that rank 1 vs rank 2
# isn't a cliff, small enough that the top of each list still matters most.
RRF_K = 60
# How many fused candidates the reranker re-scores: enough to rescue a good excerpt ranked 15th,
# few enough to keep a query well under 100 ms on a laptop CPU.
RERANK_POOL = 20


class Retriever:
    """Embeds a query and ranks matching chunks from the vector store."""

    def __init__(
        self,
        store: VectorStore,
        embedder: Embedder,
        reranker: Reranker | None = None,
        keyword_weighting: Callable[[str], float] = keyword_weight,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._reranker = reranker
        self._keyword_weighting = keyword_weighting

    def retrieve(
        self, query: str, top_k: int = DEFAULT_TOP_K, modified_after: datetime | None = None
    ) -> list[SearchResult]:
        """The top_k chunks for query, best first, by fused vector + keyword rank, keyword rank
        counting only for exact-sounding queries (codes, names). A recency filter applies to the
        vector side only, so keyword hits are filtered afterwards."""
        reranking = self._reranker is not None and self._reranker.is_ready()
        candidates = max(top_k, RERANK_POOL if reranking else 0) * CANDIDATE_MULTIPLIER
        semantic = self._store.search(
            self._embedder.embed_query(query), top_k=candidates, modified_after=modified_after
        )
        weight = self._keyword_weighting(query)
        keyword = self._store.search_text(query, top_k=candidates) if weight > 0 else []
        if modified_after is not None:
            keyword = [r for r in keyword if r.metadata["modified_at"] >= modified_after]
        fused = fuse_rankings([semantic, keyword], [1.0, weight])
        if reranking and self._reranker is not None:
            return self._reranker.rerank(query, fused[: max(top_k, RERANK_POOL)], top_k)
        return fused[:top_k]

    def retrieve_semantic_only(self, query: str, top_k: int = DEFAULT_TOP_K) -> list[SearchResult]:
        """Vector search alone, kept for the retrieval benchmark's before/after comparison."""
        return self._store.search(self._embedder.embed_query(query), top_k=top_k)


def fuse_rankings(rankings: list[list[SearchResult]], weights: list[float] | None = None) -> list[SearchResult]:
    """Weighted reciprocal rank fusion: each chunk scores sum(weight / (RRF_K + rank)) over the
    lists it appears in (every weight 1 by default). Rank-based, so vector distances and BM25
    scores never need to be compared. The returned results carry the fused score, higher
    meaning more relevant."""
    fused: dict[str, float] = {}
    by_id: dict[str, SearchResult] = {}
    for ranking, weight in zip(rankings, weights or [1.0] * len(rankings), strict=True):
        for rank, result in enumerate(ranking, start=1):
            fused[result.chunk_id] = fused.get(result.chunk_id, 0.0) + weight / (RRF_K + rank)
            by_id.setdefault(result.chunk_id, result)
    ordered = sorted(fused, key=fused.__getitem__, reverse=True)
    return [by_id[chunk_id].model_copy(update={"score": fused[chunk_id]}) for chunk_id in ordered]
