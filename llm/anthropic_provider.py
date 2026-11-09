"""
Talks to Anthropic's Messages API: plain completions, tool-calling chat turns, and model listing.
Does not know about prompts, retrieval, or what tools do; message-format conversion lives in
anthropic_messages.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import anthropic

from core.exceptions import ProviderError
from core.logger import get_logger
from llm.anthropic_messages import to_anthropic_messages, to_anthropic_tools, tool_calls_from_message
from models.chat import ChatMessage, TextDelta, ToolCall, ToolSpec

logger = get_logger(__name__)

MAX_TOKENS = 2048


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

    def stream_chat(
        self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> Iterator[TextDelta | ToolCall]:
        """
        Runs one model turn, streaming its answer text and then any tools it wants called.

        A tool_use block's input is only complete once the message is, so every TextDelta comes
        before the first ToolCall.

        Args:
            system: The system prompt.
            messages: The conversation so far, oldest first.
            tools: Tools the model may call; empty means a plain answer.

        Yields:
            TextDelta slices as they stream, then one ToolCall per tool_use block.
        """
        try:
            with self._client.messages.stream(**self._chat_request(system, messages, tools)) as stream:
                for event in stream:
                    if event.type == "content_block_delta" and event.delta.type == "text_delta":
                        yield TextDelta(text=event.delta.text)
                final_message = stream.get_final_message()
        except anthropic.AnthropicError as e:
            raise ProviderError(
                f"Anthropic chat failed ({self._model}): {e}. Check the API key and model name in Settings."
            ) from e
        yield from tool_calls_from_message(final_message)

    def list_models(self) -> list[str]:
        """Ids of the models this API key can use, sorted."""
        try:
            return sorted(model.id for model in self._client.models.list())
        except anthropic.AnthropicError as e:
            raise ProviderError(f"Couldn't list Anthropic models: {e}. Check the API key in Settings.") from e

    def is_available(self) -> bool:
        """True if the API responds to a lightweight models-list call."""
        try:
            self._client.models.list(limit=1)
            return True
        except anthropic.AnthropicError:
            return False

    def _chat_request(self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]) -> dict[str, Any]:
        """Keyword arguments for messages.stream; system and tools are left out when empty."""
        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": MAX_TOKENS,
            "messages": to_anthropic_messages(messages),
        }
        if system:
            request["system"] = system
        if tools:
            request["tools"] = to_anthropic_tools(tools)
        return request
