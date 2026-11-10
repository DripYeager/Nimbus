from __future__ import annotations

from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

from core.exceptions import ProviderError
from llm.anthropic_provider import AnthropicProvider
from llm.ollama_provider import OllamaProvider
from llm.openai_provider import OpenAIProvider
from llm.provider import PLACEHOLDER_LOCAL_KEY, build_provider, get_provider, provider_config_from_settings
from models.chat import ProviderConfig


def _fake_settings(provider: str) -> SimpleNamespace:
    return SimpleNamespace(
        llm_provider=provider,
        ollama_host="http://localhost:11434",
        ollama_model="llama3.1:8b",
        ollama_context_tokens=16384,
        anthropic_model="claude-haiku-5-5",
        openai_model="gpt-5-mini",
        compatible_base_url="https://api.deepinfra.com/v1/openai",
        compatible_model="deepseek-ai/DeepSeek-V3",
    )


@pytest.fixture(autouse=True)
def _mock_sdks(mocker: MockerFixture) -> None:
    mocker.patch("llm.ollama_provider.ollama.Client")
    mocker.patch("llm.openai_provider.openai.OpenAI")
    mocker.patch("llm.anthropic_provider.anthropic.Anthropic")


@pytest.fixture(autouse=True)
def _mock_api_key(mocker: MockerFixture) -> None:
    mocker.patch("llm.provider.get_api_key", return_value="stored-key")


def test_build_provider_builds_ollama_on_the_given_host(mocker: MockerFixture) -> None:
    client = mocker.patch("llm.ollama_provider.ollama.Client")
    provider = build_provider(ProviderConfig(name="ollama", model="llama3.1:8b"), ollama_host="http://box:11434")
    assert isinstance(provider, OllamaProvider)
    client.assert_called_once_with(host="http://box:11434")


def test_build_provider_falls_back_to_the_settings_ollama_host(mocker: MockerFixture) -> None:
    mocker.patch("llm.provider.get_settings", return_value=_fake_settings("ollama"))
    client = mocker.patch("llm.ollama_provider.ollama.Client")
    build_provider(ProviderConfig(name="ollama", model="llama3.1:8b"))
    client.assert_called_once_with(host="http://localhost:11434")


def test_build_provider_builds_anthropic() -> None:
    config = ProviderConfig(name="anthropic", model="claude-haiku-5-5", api_key="an-key")
    assert isinstance(build_provider(config), AnthropicProvider)


def test_build_provider_builds_openai_without_a_base_url(mocker: MockerFixture) -> None:
    client = mocker.patch("llm.openai_provider.openai.OpenAI")
    build_provider(ProviderConfig(name="openai", model="gpt-5-mini", api_key="oa-key"))
    client.assert_called_once_with(api_key="oa-key", base_url=None)


def test_build_provider_points_openai_compatible_at_its_base_url(mocker: MockerFixture) -> None:
    client = mocker.patch("llm.openai_provider.openai.OpenAI")
    config = ProviderConfig(name="openai_compatible", model="qwen", base_url="http://localhost:1234/v1")
    assert isinstance(build_provider(config), OpenAIProvider)
    client.assert_called_once_with(api_key=PLACEHOLDER_LOCAL_KEY, base_url="http://localhost:1234/v1")


def test_build_provider_raises_for_openai_compatible_without_a_base_url() -> None:
    with pytest.raises(ProviderError, match="base URL"):
        build_provider(ProviderConfig(name="openai_compatible", model="qwen"))


def test_build_provider_raises_for_an_unrecognized_provider() -> None:
    with pytest.raises(ProviderError):
        build_provider(ProviderConfig.model_construct(name="bogus", model="x"))


def test_provider_config_from_settings_reads_the_active_model_and_key() -> None:
    config = provider_config_from_settings(_fake_settings("anthropic"))
    assert config == ProviderConfig(name="anthropic", model="claude-haiku-5-5", api_key="stored-key")


def test_provider_config_from_settings_leaves_base_url_unset_for_openai() -> None:
    assert provider_config_from_settings(_fake_settings("openai")).base_url is None


def test_provider_config_from_settings_reads_the_compatible_server_details() -> None:
    compatible = provider_config_from_settings(_fake_settings("openai_compatible"))
    assert compatible.base_url == "https://api.deepinfra.com/v1/openai"
    assert compatible.model == "deepseek-ai/DeepSeek-V3"


def test_get_provider_builds_the_provider_selected_in_settings() -> None:
    assert isinstance(get_provider(_fake_settings("openai")), OpenAIProvider)


def test_get_provider_defaults_to_get_settings_when_none_is_given(mocker: MockerFixture) -> None:
    """Omitting settings must fall back to the real get_settings() call, not silently do nothing."""
    mocker.patch("llm.provider.get_settings", return_value=_fake_settings("ollama"))
    assert isinstance(get_provider(), OllamaProvider)
