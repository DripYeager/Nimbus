"""
Defines the provider-agnostic contract every LLM backend implements, and the factory that
picks a concrete backend from settings. Does not implement any provider itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from config.settings import Settings, get_settings
from core.exceptions import ProviderError
from llm.anthropic_provider import AnthropicProvider
from llm.deepinfra_provider import DeepInfraProvider
from llm.ollama_provider import OllamaProvider
from llm.openai_provider import OpenAIProvider


class LLMProvider(Protocol):
    """The model-agnostic contract every backend implements."""

    def complete(self, prompt: str) -> str: ...

    def stream(self, prompt: str) -> Iterator[str]: ...

    def is_available(self) -> bool: ...


def get_provider(settings: Settings | None = None) -> LLMProvider:
    """Builds the concrete provider selected by settings.llm_provider."""
    settings = settings or get_settings()
    if settings.llm_provider == "ollama":
        return OllamaProvider(settings.ollama_host, settings.ollama_model)
    if settings.llm_provider == "deepinfra":
        return DeepInfraProvider(settings.deepinfra_api_key, settings.deepinfra_model)
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model)
    if settings.llm_provider == "openai":
        return OpenAIProvider(settings.openai_api_key, settings.openai_model)
    raise ProviderError(f"Unknown llm_provider: {settings.llm_provider}")
