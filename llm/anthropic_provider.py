"""
Talks to Anthropic's Messages API for Claude completions.
Does not know about prompts, retrieval, or intents; it only turns a prompt into text.
"""

from __future__ import annotations

from collections.abc import Iterator

import anthropic

from core.exceptions import ProviderError
from core.logger import get_logger

logger = get_logger(__name__)

MAX_TOKENS = 1024


class AnthropicProvider:
    """Implements LLMProvider against Anthropic's Messages API."""

    def __init__(self, api_key: str | None, model: str) -> None:
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, prompt: str) -> str:
        """Sends prompt to the Messages API and returns the full response text."""
        try:
            response = self._client.messages.create(
                model=self._model, max_tokens=MAX_TOKENS, messages=[{"role": "user", "content": prompt}]
            )
        except anthropic.AnthropicError as e:
            raise ProviderError(f"Anthropic request failed ({self._model}): {e}") from e
        return response.content[0].text if response.content else ""

    def stream(self, prompt: str) -> Iterator[str]:
        """Sends prompt to the Messages API and yields response text as it streams in."""
        try:
            with self._client.messages.stream(
                model=self._model, max_tokens=MAX_TOKENS, messages=[{"role": "user", "content": prompt}]
            ) as stream:
                yield from stream.text_stream
        except anthropic.AnthropicError as e:
            raise ProviderError(f"Anthropic stream failed ({self._model}): {e}") from e

    def is_available(self) -> bool:
        """True if the API responds to a lightweight models-list call."""
        try:
            self._client.models.list(limit=1)
            return True
        except anthropic.AnthropicError:
            return False
