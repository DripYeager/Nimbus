"""
Talks to DeepInfra's OpenAI-compatible API for DeepSeek model completions.
Does not know about prompts, retrieval, or intents; it only turns a prompt into text.
"""

from __future__ import annotations

from llm.openai_provider import OpenAIProvider

DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/openai"


class DeepInfraProvider(OpenAIProvider):
    """Implements LLMProvider against DeepInfra — same request logic as OpenAIProvider,
    just aimed at a different base_url, since DeepInfra's API is OpenAI-compatible."""

    def __init__(self, api_key: str | None, model: str) -> None:
        super().__init__(api_key=api_key, model=model, base_url=DEEPINFRA_BASE_URL)
