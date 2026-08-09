"""
Talks to OpenAI's chat completions API for cloud-hosted answers.
Does not know about prompts, retrieval, or intents; it only turns a prompt into text.
"""

from __future__ import annotations

from collections.abc import Iterator

import openai

from core.exceptions import ProviderError
from core.logger import get_logger

logger = get_logger(__name__)


class OpenAIProvider:
    """Implements LLMProvider against OpenAI's chat completions API, or any API compatible
    with it — see deepinfra_provider.py, which reuses this class with a different base_url."""

    def __init__(self, api_key: str | None, model: str, base_url: str | None = None) -> None:
        self._model = model
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url)

    def complete(self, prompt: str) -> str:
        """Sends prompt to the chat completions API and returns the full response text."""
        try:
            response = self._client.chat.completions.create(
                model=self._model, messages=[{"role": "user", "content": prompt}]
            )
        except openai.OpenAIError as e:
            raise ProviderError(f"Chat completion request failed ({self._model}): {e}") from e
        return response.choices[0].message.content or ""

    def stream(self, prompt: str) -> Iterator[str]:
        """Sends prompt to the chat completions API and yields response text as it streams in."""
        try:
            events = self._client.chat.completions.create(
                model=self._model, messages=[{"role": "user", "content": prompt}], stream=True
            )
            for event in events:
                delta = event.choices[0].delta.content
                if delta:
                    yield delta
        except openai.OpenAIError as e:
            raise ProviderError(f"Chat completion stream failed ({self._model}): {e}") from e

    def is_available(self) -> bool:
        """True if the API responds to a lightweight models-list call."""
        try:
            self._client.models.list()
            return True
        except openai.OpenAIError:
            return False
