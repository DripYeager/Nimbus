"""Provider-agnostic LLM access — Ollama, DeepInfra, Anthropic, or OpenAI behind one interface."""

from __future__ import annotations

from llm.anthropic_provider import AnthropicProvider
from llm.deepinfra_provider import DeepInfraProvider
from llm.ollama_provider import OllamaProvider
from llm.openai_provider import OpenAIProvider
from llm.prompts import build_intent_classify_prompt, build_qa_prompt, build_summarize_prompt
from llm.provider import LLMProvider, get_provider

__all__ = [
    "LLMProvider",
    "get_provider",
    "OllamaProvider",
    "DeepInfraProvider",
    "AnthropicProvider",
    "OpenAIProvider",
    "build_summarize_prompt",
    "build_qa_prompt",
    "build_intent_classify_prompt",
]
