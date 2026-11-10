"""
Talks to a local Ollama server, the default, fully local LLM backend: plain completions,
tool-calling chat turns, and model listing. Does not know about prompts, retrieval, or what tools
do; message-format conversion lives in ollama_messages.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import ollama

from core.exceptions import ProviderError, ToolsUnsupportedError
from core.logger import get_logger
from llm.ollama_messages import to_ollama_messages, to_ollama_tools, to_tool_call
from models.chat import ChatMessage, TextDelta, ToolCall, ToolSpec

logger = get_logger(__name__)

# Ollama wraps a bad response as ResponseError and "connection refused" as a bare
# ConnectionError, but doesn't wrap everything else (timeouts, DNS failures), those
# still surface as raw httpx errors, so httpx.HTTPError is needed to catch the rest.
OLLAMA_ERRORS = (ollama.RequestError, ollama.ResponseError, ConnectionError, httpx.HTTPError)

# What Ollama says when a model's template has no tool support.
TOOLS_UNSUPPORTED_MARKER = "does not support tools"
DEFAULT_CONTEXT_TOKENS = 16384


class OllamaProvider:
    """Implements LLMProvider against a local Ollama server."""

    def __init__(self, host: str, model: str, context_tokens: int = DEFAULT_CONTEXT_TOKENS) -> None:
        self._host = host
        self._model = model
        self._options = {"num_ctx": context_tokens}
        self._client = ollama.Client(host=host)

    def complete(self, prompt: str) -> str:
        """Sends prompt to Ollama and returns the full response text."""
        try:
            response = self._client.chat(
                model=self._model, messages=[{"role": "user", "content": prompt}], options=self._options
            )
        except OLLAMA_ERRORS as e:
            raise ProviderError(f"Ollama request failed ({self._model} @ {self._host}): {e}") from e
        return response.message.content or ""

    def stream(self, prompt: str) -> Iterator[str]:
        """Sends prompt to Ollama and yields response text as it streams in."""
        try:
            chunks = self._client.chat(
                model=self._model, messages=[{"role": "user", "content": prompt}], stream=True, options=self._options
            )
            for chunk in chunks:
                if chunk.message.content:
                    yield chunk.message.content
        except OLLAMA_ERRORS as e:
            raise ProviderError(f"Ollama stream failed ({self._model} @ {self._host}): {e}") from e

    def stream_chat(
        self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> Iterator[TextDelta | ToolCall]:
        """
        Runs one model turn, yielding answer text and tool calls in the order Ollama streams them.

        Ollama sends each tool call whole in a single chunk, so a ToolCall can be yielded before
        the stream ends rather than strictly after all the text.

        Args:
            system: The system prompt.
            messages: The conversation so far, oldest first.
            tools: Tools the model may call; empty means a plain answer.

        Raises:
            ToolsUnsupportedError: The model can't call tools, so the caller should fall back.
            ProviderError: Any other failure talking to Ollama.
        """
        try:
            for chunk in self._client.chat(**self._chat_request(system, messages, tools)):
                if chunk.message.content:
                    yield TextDelta(text=chunk.message.content)
                for call in chunk.message.tool_calls or []:
                    yield to_tool_call(call)
        except OLLAMA_ERRORS as e:
            raise self._chat_error(e) from e

    def list_models(self) -> list[str]:
        """Names of the models pulled on this Ollama server, sorted."""
        try:
            response = self._client.list()
        except OLLAMA_ERRORS as e:
            raise ProviderError(f"Couldn't list Ollama models at {self._host}: {e}. Is Ollama running?") from e
        return sorted(model.model for model in response.models if model.model)

    def is_available(self) -> bool:
        """True if the Ollama server responds at all."""
        try:
            self._client.list()
            return True
        except OLLAMA_ERRORS:
            return False

    def _chat_request(self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]) -> dict[str, Any]:
        """Keyword arguments for a streamed chat; tools are left out when empty."""
        request: dict[str, Any] = {
            "model": self._model,
            "messages": to_ollama_messages(system, messages),
            "stream": True,
            "options": self._options,
        }
        if tools:
            request["tools"] = to_ollama_tools(tools)
        return request

    def _chat_error(self, error: Exception) -> ProviderError:
        """Maps an Ollama failure to the domain error the caller should handle."""
        if isinstance(error, ollama.ResponseError) and TOOLS_UNSUPPORTED_MARKER in str(error.error):
            return ToolsUnsupportedError(
                f"{self._model} can't call tools. Pick a tool-capable model (e.g. llama3.1, qwen2.5) in Settings."
            )
        return ProviderError(f"Ollama chat failed ({self._model} @ {self._host}): {error}. Is Ollama running?")
