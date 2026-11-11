"""
Defines the provider-agnostic contract every LLM backend implements, and the factory that
builds a concrete backend from a ProviderConfig. Does not implement any provider itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from config.settings import Settings, get_settings
from core.exceptions import ProviderError
from core.secret_store import get_api_key
from models.chat import ChatMessage, ProviderConfig, TextDelta, ToolCall, ToolSpec

# The OpenAI SDK insists on some key, but local OpenAI-compatible servers (LM Studio, vLLM)
# don't check it.
PLACEHOLDER_LOCAL_KEY = "not-needed"


class LLMProvider(Protocol):
    """The model-agnostic contract every backend implements."""

    def complete(self, prompt: str) -> str: ...

    def stream(self, prompt: str) -> Iterator[str]: ...

    def stream_chat(
        self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> Iterator[TextDelta | ToolCall]: ...

    def list_models(self) -> list[str]: ...

    def is_available(self) -> bool: ...


def build_provider(config: ProviderConfig, ollama_host: str | None = None) -> LLMProvider:
    """Builds the concrete provider config describes. Each backend is imported only when chosen:
    the cloud SDKs take over two seconds to load, which a local-only user shouldn't pay."""
    if config.name == "ollama":
        from llm.ollama_provider import OllamaProvider

        settings = get_settings()
        return OllamaProvider(
            ollama_host or settings.ollama_host, config.model, settings.ollama_context_tokens, settings.ollama_thinking
        )
    if config.name == "anthropic":
        from llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(config.api_key, config.model)
    from llm.openai_provider import OpenAIProvider

    if config.name == "openai":
        return OpenAIProvider(config.api_key, config.model)
    if config.name == "openai_compatible":
        if not config.base_url:
            raise ProviderError("An OpenAI-compatible provider needs a base URL. Set one in Settings → Model.")
        return OpenAIProvider(config.api_key or PLACEHOLDER_LOCAL_KEY, config.model, base_url=config.base_url)
    raise ProviderError(f"Unknown provider: {config.name}")


def provider_config_from_settings(settings: Settings) -> ProviderConfig:
    """Reads the active provider's model, key and URL out of settings and the credential store."""
    name = settings.llm_provider
    models = {
        "ollama": settings.ollama_model,
        "openai": settings.openai_model,
        "anthropic": settings.anthropic_model,
        "openai_compatible": settings.compatible_model,
    }
    base_url = settings.compatible_base_url if name == "openai_compatible" else None
    return ProviderConfig(name=name, model=models[name], api_key=get_api_key(name, settings), base_url=base_url)


def get_provider(settings: Settings | None = None) -> LLMProvider:
    """Builds the provider currently selected in settings."""
    settings = settings or get_settings()
    return build_provider(provider_config_from_settings(settings), ollama_host=settings.ollama_host)
