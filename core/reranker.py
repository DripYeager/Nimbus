"""
Re-orders search candidates with a small cross-encoder (fastembed's ONNX Jina reranker), which
reads the question and each excerpt together instead of comparing two separate vectors, so it
judges relevance more precisely than the first-pass search. Its 8K-token window reads whole
excerpts; a 512-token model tried first missed facts near the end of long ones. The model loads
(and downloads once, about 150 MB) in the background; until it's ready, or if it can't load,
search simply runs without it. Owns re-scoring only; finding the candidates is the retriever's job.
"""

from __future__ import annotations

import threading

from fastembed.rerank.cross_encoder import TextCrossEncoder

from config.paths import model_cache_dir
from config.settings import get_settings
from core.logger import get_logger
from models.schema import SearchResult

logger = get_logger(__name__)


class Reranker:
    """Thread-safe: load() may run on a background thread while searches call rerank()."""

    def __init__(self, model_name: str, threads: int) -> None:
        self._model_name = model_name
        self._threads = threads
        self._model: TextCrossEncoder | None = None
        self._failed = False
        self._lock = threading.Lock()

    def is_ready(self) -> bool:
        return self._model is not None

    def load_in_background(self) -> None:
        threading.Thread(target=self.load, name="reranker-load", daemon=True).start()

    def load(self) -> None:
        """Loads the model once; a failure (offline first run, say) is logged and remembered."""
        with self._lock:
            if self._model is not None or self._failed:
                return
            try:
                logger.info("Loading reranker", extra={"model": self._model_name})
                self._model = TextCrossEncoder(
                    self._model_name, cache_dir=str(model_cache_dir()), threads=self._threads
                )
            except Exception as e:
                self._failed = True
                logger.warning(
                    "Reranker unavailable, search runs without it", extra={"model": self._model_name, "error": str(e)}
                )

    def rerank(self, query: str, candidates: list[SearchResult], top_k: int) -> list[SearchResult]:
        """The top_k candidates by cross-encoder score, or the first top_k unchanged when the
        model isn't ready or fails on this query."""
        model = self._model
        if model is None or len(candidates) < 2:
            return candidates[:top_k]
        try:
            scores = list(model.rerank(query, [candidate.chunk_text for candidate in candidates]))
        except Exception as e:
            logger.warning("Reranking failed, keeping the first-pass order", extra={"error": str(e)})
            return candidates[:top_k]
        ranked = [
            candidate for _, candidate in sorted(zip(scores, candidates, strict=True), key=lambda p: p[0], reverse=True)
        ]
        # Blended with the first-pass order rather than replacing it: the model reads only the
        # start of a long excerpt, and on its own it overruled correct hits in the benchmark.
        return blend(candidates, ranked)[:top_k]


def blend(first_pass: list[SearchResult], reranked: list[SearchResult]) -> list[SearchResult]:
    """Both orders fused by reciprocal rank, the same way vector and keyword search are."""
    from core.retriever import fuse_rankings

    return fuse_rankings([first_pass, reranked])


_reranker: Reranker | None = None


def get_reranker() -> Reranker | None:
    """The process-wide Reranker, or None when reranking is switched off in settings."""
    global _reranker
    settings = get_settings()
    if not settings.rerank_enabled:
        return None
    if _reranker is None:
        _reranker = Reranker(settings.rerank_model, settings.embedding_threads)
    return _reranker
