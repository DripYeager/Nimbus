from __future__ import annotations

from types import SimpleNamespace

import anthropic
import pytest
from pytest_mock import MockerFixture

from core.exceptions import ProviderError
from llm.anthropic_provider import AnthropicProvider


@pytest.fixture
def provider(mocker: MockerFixture) -> AnthropicProvider:
    mocker.patch("llm.anthropic_provider.anthropic.Anthropic")
    return AnthropicProvider(api_key="sk-ant-test", model="claude-3-5-haiku-latest")


def _fake_stream(mocker: MockerFixture, text_chunks: list[str]) -> object:
    manager = mocker.MagicMock()
    manager.__enter__.return_value = SimpleNamespace(text_stream=iter(text_chunks))
    return manager


def test_complete_returns_the_response_text(provider: AnthropicProvider) -> None:
    provider._client.messages.create.return_value = SimpleNamespace(content=[SimpleNamespace(text="hello there")])
    assert provider.complete("hi") == "hello there"


def test_complete_returns_empty_string_when_content_is_empty(provider: AnthropicProvider) -> None:
    provider._client.messages.create.return_value = SimpleNamespace(content=[])
    assert provider.complete("hi") == ""


def test_complete_raises_provider_error_when_the_request_fails(provider: AnthropicProvider) -> None:
    provider._client.messages.create.side_effect = anthropic.AnthropicError("overloaded")
    with pytest.raises(ProviderError):
        provider.complete("hi")


def test_complete_does_not_swallow_an_unrelated_bug(provider: AnthropicProvider) -> None:
    provider._client.messages.create.side_effect = ValueError("caller passed the wrong type")
    with pytest.raises(ValueError):
        provider.complete("hi")


def test_stream_yields_the_text_stream(provider: AnthropicProvider, mocker: MockerFixture) -> None:
    provider._client.messages.stream.return_value = _fake_stream(mocker, ["hel", "lo"])
    assert list(provider.stream("hi")) == ["hel", "lo"]


def test_stream_raises_provider_error_when_the_request_fails(provider: AnthropicProvider) -> None:
    provider._client.messages.stream.side_effect = anthropic.AnthropicError("overloaded")
    with pytest.raises(ProviderError):
        list(provider.stream("hi"))


def test_is_available_returns_true_when_the_api_responds(provider: AnthropicProvider) -> None:
    provider._client.models.list.return_value = SimpleNamespace(data=[])
    assert provider.is_available() is True


def test_is_available_returns_false_when_the_api_is_unreachable(provider: AnthropicProvider) -> None:
    provider._client.models.list.side_effect = anthropic.AnthropicError("network error")
    assert provider.is_available() is False
