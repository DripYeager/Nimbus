"""Provider-agnostic LLM access — Ollama, Anthropic, OpenAI, or any OpenAI-compatible server behind one interface."""

from __future__ import annotations

from llm.active_provider import ActiveProvider
from llm.anthropic_provider import AnthropicProvider
from llm.ollama_provider import OllamaProvider
from llm.openai_provider import OpenAIProvider
from llm.prompts import build_qa_prompt, build_summarize_prompt, build_system_prompt
from llm.provider import LLMProvider, build_provider, get_provider, provider_config_from_settings

__all__ = [
    "LLMProvider",
    "get_provider",
    "build_provider",
    "provider_config_from_settings",
    "OllamaProvider",
    "AnthropicProvider",
    "OpenAIProvider",
    "build_summarize_prompt",
    "build_qa_prompt",
    "build_system_prompt",
    "ActiveProvider",
]
