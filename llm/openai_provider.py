"""
Talks to OpenAI's chat completions API, or any server compatible with it: plain completions,
tool-calling chat turns, and model listing. Does not know about prompts, retrieval, or what tools
do; message-format conversion lives in openai_messages.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import openai

from core.exceptions import ProviderError
from core.logger import get_logger
from llm.openai_messages import (
    ToolCallFragments,
    add_tool_call_fragments,
    finish_tool_calls,
    to_openai_messages,
    to_openai_tools,
)
from models.chat import ChatMessage, TextDelta, ToolCall, ToolSpec

logger = get_logger(__name__)

# OpenAI's models endpoint also lists embedding, audio, image and moderation models;
# only these prefixes can hold a chat.
CHAT_MODEL_PREFIXES = ("gpt-", "o1", "o3", "o4", "chatgpt")
MISSING_KEY_PLACEHOLDER = "missing-api-key"


class OpenAIProvider:
    """Implements LLMProvider against OpenAI's chat completions API, or — given a base_url — any
    OpenAI-compatible server (DeepInfra, LM Studio, vLLM)."""

    def __init__(self, api_key: str | None, model: str, base_url: str | None = None) -> None:
        self._model = model
        self._base_url = base_url
        # The SDK refuses to build a client with no key at all, but the provider must exist before
        # the user has entered one (onboarding saves the provider choice before the key). A
        # placeholder lets it build; the first real call then fails with the API's own
        # "invalid key" error, wrapped as a ProviderError like any other.
        resolved_key = api_key or MISSING_KEY_PLACEHOLDER
        self._client = openai.OpenAI(api_key=resolved_key, base_url=base_url)

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

    def stream_chat(
        self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> Iterator[TextDelta | ToolCall]:
        """
        Runs one model turn, streaming its answer text and then any tools it wants called.

        Tool-call arguments stream in as JSON fragments, so calls are only yielded once the stream
        ends; every TextDelta comes before the first ToolCall.

        Args:
            system: The system prompt.
            messages: The conversation so far, oldest first.
            tools: Tools the model may call; empty means a plain answer.

        Yields:
            TextDelta slices as they stream, then one ToolCall per requested call.
        """
        fragments: ToolCallFragments = {}
        try:
            for chunk in self._client.chat.completions.create(**self._chat_request(system, messages, tools)):
                # Some servers send a trailing usage-only chunk with no choices.
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    yield TextDelta(text=delta.content)
                add_tool_call_fragments(fragments, delta.tool_calls or [])
        except openai.OpenAIError as e:
            raise ProviderError(
                f"Chat request failed ({self._model}): {e}. Check the API key, model name and server URL in Settings."
            ) from e
        yield from finish_tool_calls(fragments)

    def list_models(self) -> list[str]:
        """Model ids from the models endpoint, sorted. On OpenAI itself only chat models are kept;
        a compatible server's ids come back unfiltered since its naming can't be predicted."""
        try:
            ids = [model.id for model in self._client.models.list()]
        except openai.OpenAIError as e:
            raise ProviderError(f"Couldn't list models: {e}. Check the API key and server URL in Settings.") from e
        if not self._base_url:
            ids = [model_id for model_id in ids if model_id.startswith(CHAT_MODEL_PREFIXES)]
        return sorted(ids)

    def is_available(self) -> bool:
        """True if the API responds to a lightweight models-list call."""
        try:
            self._client.models.list()
            return True
        except openai.OpenAIError:
            return False

    def _chat_request(self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]) -> dict[str, Any]:
        """Keyword arguments for a streamed chat completion; tools are left out when empty."""
        request: dict[str, Any] = {
            "model": self._model,
            "messages": to_openai_messages(system, messages),
            "stream": True,
        }
        if tools:
            request["tools"] = to_openai_tools(tools)
        return request
