from __future__ import annotations

from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

from core.exceptions import ProviderError
from llm.anthropic_provider import AnthropicProvider
from llm.deepinfra_provider import DeepInfraProvider
from llm.ollama_provider import OllamaProvider
from llm.openai_provider import OpenAIProvider
from llm.provider import get_provider


def _fake_settings(provider: str) -> SimpleNamespace:
    return SimpleNamespace(
        llm_provider=provider,
        ollama_host="http://localhost:11434",
        ollama_model="llama3.1:8b",
        deepinfra_api_key="di-key",
        deepinfra_model="deepseek-ai/DeepSeek-V4-Flash-0731",
        anthropic_api_key="an-key",
        anthropic_model="claude-3-5-haiku-latest",
        openai_api_key="oa-key",
        openai_model="gpt-4o-mini",
    )


@pytest.fixture(autouse=True)
def _mock_sdks(mocker: MockerFixture) -> None:
    mocker.patch("llm.ollama_provider.ollama.Client")
    mocker.patch("llm.openai_provider.openai.OpenAI")
    mocker.patch("llm.anthropic_provider.anthropic.Anthropic")


def test_get_provider_selects_ollama() -> None:
    assert isinstance(get_provider(_fake_settings("ollama")), OllamaProvider)


def test_get_provider_selects_deepinfra() -> None:
    assert isinstance(get_provider(_fake_settings("deepinfra")), DeepInfraProvider)


def test_get_provider_selects_anthropic() -> None:
    assert isinstance(get_provider(_fake_settings("anthropic")), AnthropicProvider)


def test_get_provider_selects_openai() -> None:
    assert isinstance(get_provider(_fake_settings("openai")), OpenAIProvider)


def test_get_provider_raises_for_an_unrecognized_provider() -> None:
    with pytest.raises(ProviderError):
        get_provider(_fake_settings("bogus"))


def test_get_provider_defaults_to_get_settings_when_none_is_given(mocker: MockerFixture) -> None:
    """Omitting settings must fall back to the real get_settings() call, not silently do nothing."""
    mocker.patch("llm.provider.get_settings", return_value=_fake_settings("openai"))
    assert isinstance(get_provider(), OpenAIProvider)
