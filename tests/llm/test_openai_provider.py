from __future__ import annotations

from types import SimpleNamespace

import openai
import pytest
from pytest_mock import MockerFixture

from core.exceptions import ProviderError
from llm.openai_provider import OpenAIProvider


@pytest.fixture
def provider(mocker: MockerFixture) -> OpenAIProvider:
    mocker.patch("llm.openai_provider.openai.OpenAI")
    return OpenAIProvider(api_key="sk-test", model="gpt-4o-mini")


def test_complete_returns_the_response_text(provider: OpenAIProvider) -> None:
    provider._client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="hello there"))]
    )
    assert provider.complete("hi") == "hello there"


def test_complete_raises_provider_error_when_the_request_fails(provider: OpenAIProvider) -> None:
    provider._client.chat.completions.create.side_effect = openai.OpenAIError("rate limited")
    with pytest.raises(ProviderError):
        provider.complete("hi")


def test_complete_does_not_swallow_an_unrelated_bug(provider: OpenAIProvider) -> None:
    provider._client.chat.completions.create.side_effect = ValueError("caller passed the wrong type")
    with pytest.raises(ValueError):
        provider.complete("hi")


def test_stream_yields_each_deltas_text(provider: OpenAIProvider) -> None:
    provider._client.chat.completions.create.return_value = [
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="hel"))]),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="lo"))]),
    ]
    assert list(provider.stream("hi")) == ["hel", "lo"]


def test_stream_skips_deltas_with_no_content(provider: OpenAIProvider) -> None:
    provider._client.chat.completions.create.return_value = [
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="hel"))]),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None))]),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="lo"))]),
    ]
    assert list(provider.stream("hi")) == ["hel", "lo"]


def test_stream_raises_provider_error_when_the_request_fails(provider: OpenAIProvider) -> None:
    provider._client.chat.completions.create.side_effect = openai.OpenAIError("rate limited")
    with pytest.raises(ProviderError):
        list(provider.stream("hi"))


def test_is_available_returns_true_when_the_api_responds(provider: OpenAIProvider) -> None:
    provider._client.models.list.return_value = SimpleNamespace(data=[])
    assert provider.is_available() is True


def test_is_available_returns_false_when_the_api_is_unreachable(provider: OpenAIProvider) -> None:
    provider._client.models.list.side_effect = openai.OpenAIError("network error")
    assert provider.is_available() is False
