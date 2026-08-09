"""
Turns text into vectors using a local sentence-transformers model — the only place Nimbus embeds text.
Does not know about files, chunks, or the vector store; it only converts text to numbers.
"""

from __future__ import annotations

from sentence_transformers import SentenceTransformer

from config.settings import get_settings
from core.exceptions import IndexingError
from core.logger import get_logger

logger = get_logger(__name__)


class Embedder:
    """Wraps a loaded sentence-transformers model for batch text-to-vector encoding."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model: SentenceTransformer | None = None

    def load(self) -> None:
        """Loads the model into memory. Safe to call more than once."""
        if self._model is not None:
            return
        try:
            logger.info("Loading embedding model", extra={"model": self._model_name})
            self._model = SentenceTransformer(self._model_name)
        except Exception as e:
            raise IndexingError(f"Couldn't load embedding model '{self._model_name}': {e}") from e

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Encodes a batch of texts into vectors, loading the model on first use."""
        if not texts:
            return []
        self.load()
        try:
            vectors = self._model.encode(texts, convert_to_numpy=True)
        except Exception as e:
            raise IndexingError(f"Failed to embed {len(texts)} chunk(s): {e}") from e
        return [vector.tolist() for vector in vectors]


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    """Returns the process-wide Embedder singleton, built from settings on first call."""
    global _embedder
    if _embedder is None:
        _embedder = Embedder(get_settings().embedding_model)
    return _embedder
