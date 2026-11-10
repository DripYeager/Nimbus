"""
Turns text into vectors with a local ONNX embedding model (fastembed), the only place Nimbus
embeds text. No torch, no GPU, no network after the one-time model download. Does not know
about files, chunks, or the vector store.
"""

from __future__ import annotations

import threading

from fastembed import TextEmbedding

from config.paths import model_cache_dir
from config.settings import get_settings
from core.exceptions import IndexingError
from core.logger import get_logger

logger = get_logger(__name__)

EMBED_BATCH_SIZE = 32


class Embedder:
    """Wraps a loaded fastembed model. Documents and queries are embedded differently, bge
    models expect a short instruction prefix on queries, which query_embed adds for us."""

    def __init__(self, model_name: str, threads: int) -> None:
        self._model_name = model_name
        self._threads = threads
        self._model: TextEmbedding | None = None
        self._load_lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._model_name

    def load(self) -> None:
        """Loads (downloading on first ever run) the model. Safe to call from several threads."""
        with self._load_lock:
            if self._model is not None:
                return
            try:
                logger.info("Loading embedding model", extra={"model": self._model_name})
                self._model = TextEmbedding(self._model_name, cache_dir=str(model_cache_dir()), threads=self._threads)
            except Exception as e:
                raise IndexingError(
                    f"Couldn't load embedding model '{self._model_name}': {e}. "
                    "The first run needs internet access to download it."
                ) from e

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embeds document chunks for storage."""
        if not texts:
            return []
        self.load()
        try:
            vectors = self._model.passage_embed(texts, batch_size=EMBED_BATCH_SIZE)
            return [vector.tolist() for vector in vectors]
        except Exception as e:
            raise IndexingError(f"Failed to embed {len(texts)} chunk(s): {e}") from e

    def embed_query(self, query: str) -> list[float]:
        """Embeds a search query, with the query-side instruction the model was trained on."""
        self.load()
        try:
            return next(iter(self._model.query_embed(query))).tolist()
        except Exception as e:
            raise IndexingError(f"Failed to embed the search query: {e}") from e


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    """Returns the process-wide Embedder singleton, built from settings on first call."""
    global _embedder
    if _embedder is None:
        settings = get_settings()
        _embedder = Embedder(settings.embedding_model, settings.embedding_threads)
    return _embedder
