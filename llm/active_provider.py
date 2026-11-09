"""
The provider the rest of the app talks to: a stable object that forwards every call to
whichever backend is currently selected, and counts calls against the user's daily cap.
Switching provider in Settings swaps the backend underneath without restarting anything.
Does not implement any model API itself.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

from config.settings import get_settings
from core.exceptions import UsageCapReachedError
from core.logger import get_logger
from core.usage_meter import UsageMeter
from llm.provider import LLMProvider, get_provider
from models.chat import ChatMessage, TextDelta, ToolCall, ToolSpec

logger = get_logger(__name__)


class ActiveProvider:
    """Implements LLMProvider by delegating to the current backend. Thread-safe swaps: a
    request already streaming keeps the backend it started with."""

    def __init__(self, meter: UsageMeter) -> None:
        self._meter = meter
        self._backend: LLMProvider | None = None
        self._lock = threading.Lock()

    def reload(self) -> None:
        """Rebuilds the backend from current settings — call after a provider/model/key change."""
        backend = get_provider(get_settings())
        with self._lock:
            self._backend = backend
        logger.info("Active model provider set", extra={"provider": get_settings().llm_provider})

    def complete(self, prompt: str) -> str:
        return self._metered().complete(prompt)

    def stream(self, prompt: str) -> Iterator[str]:
        return self._metered().stream(prompt)

    def stream_chat(
        self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> Iterator[TextDelta | ToolCall]:
        return self._metered().stream_chat(system, messages, tools)

    def list_models(self) -> list[str]:
        return self._current().list_models()

    def is_available(self) -> bool:
        return self._current().is_available()

    def _metered(self) -> LLMProvider:
        """The backend, after charging one call to today's usage — or refusing if capped."""
        cap = get_settings().daily_llm_call_cap
        if cap is not None and self._meter.calls_today() >= cap:
            raise UsageCapReachedError(
                f"You've used today's limit of {cap} model calls. Raise it in Settings → General, "
                "or wait until tomorrow."
            )
        self._meter.record_call()
        return self._current()

    def _current(self) -> LLMProvider:
        """The backend, built lazily on first use."""
        with self._lock:
            if self._backend is None:
                self._backend = get_provider(get_settings())
            return self._backend
