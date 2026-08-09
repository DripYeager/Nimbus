"""
Talks to a local Ollama server for completions — the default, fully local LLM backend.
Does not know about prompts, retrieval, or intents; it only turns a prompt into text.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import ollama

from core.exceptions import ProviderError
from core.logger import get_logger

logger = get_logger(__name__)

# Ollama wraps a bad response as ResponseError and "connection refused" as a bare
# ConnectionError, but doesn't wrap everything else (timeouts, DNS failures) — those
# still surface as raw httpx errors, so httpx.HTTPError is needed to catch the rest.
OLLAMA_ERRORS = (ollama.RequestError, ollama.ResponseError, ConnectionError, httpx.HTTPError)


class OllamaProvider:
    """Implements LLMProvider against a local Ollama server."""

    def __init__(self, host: str, model: str) -> None:
        self._host = host
        self._model = model
        self._client = ollama.Client(host=host)

    def complete(self, prompt: str) -> str:
        """Sends prompt to Ollama and returns the full response text."""
        try:
            response = self._client.chat(model=self._model, messages=[{"role": "user", "content": prompt}])
        except OLLAMA_ERRORS as e:
            raise ProviderError(f"Ollama request failed ({self._model} @ {self._host}): {e}") from e
        return response.message.content or ""

    def stream(self, prompt: str) -> Iterator[str]:
        """Sends prompt to Ollama and yields response text as it streams in."""
        try:
            chunks = self._client.chat(model=self._model, messages=[{"role": "user", "content": prompt}], stream=True)
            for chunk in chunks:
                if chunk.message.content:
                    yield chunk.message.content
        except OLLAMA_ERRORS as e:
            raise ProviderError(f"Ollama stream failed ({self._model} @ {self._host}): {e}") from e

    def is_available(self) -> bool:
        """True if the Ollama server responds at all."""
        try:
            self._client.list()
            return True
        except OLLAMA_ERRORS:
            return False
