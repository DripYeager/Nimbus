from __future__ import annotations

from types import SimpleNamespace

import ollama
import pytest
from pytest_mock import MockerFixture

from core.exceptions import ProviderError
from llm.ollama_provider import OllamaProvider


@pytest.fixture
def provider(mocker: MockerFixture) -> OllamaProvider:
    mocker.patch("llm.ollama_provider.ollama.Client")
    return OllamaProvider(host="http://localhost:11434", model="llama3.1:8b")


def test_complete_returns_the_response_text(provider: OllamaProvider) -> None:
    provider._client.chat.return_value = SimpleNamespace(message=SimpleNamespace(content="hello there"))
    assert provider.complete("hi") == "hello there"


def test_complete_raises_provider_error_when_the_server_is_unreachable(provider: OllamaProvider) -> None:
    provider._client.chat.side_effect = ConnectionError("connection refused")
    with pytest.raises(ProviderError):
        provider.complete("hi")


def test_complete_raises_provider_error_on_a_bad_response(provider: OllamaProvider) -> None:
    provider._client.chat.side_effect = ollama.ResponseError("model not found", 404)
    with pytest.raises(ProviderError):
        provider.complete("hi")


def test_complete_does_not_swallow_an_unrelated_bug(provider: OllamaProvider) -> None:
    provider._client.chat.side_effect = ValueError("caller passed the wrong type")
    with pytest.raises(ValueError):
        provider.complete("hi")


def test_stream_yields_each_chunks_text(provider: OllamaProvider) -> None:
    provider._client.chat.return_value = [
        SimpleNamespace(message=SimpleNamespace(content="hel")),
        SimpleNamespace(message=SimpleNamespace(content="lo")),
    ]
    assert list(provider.stream("hi")) == ["hel", "lo"]


def test_stream_skips_chunks_with_no_content(provider: OllamaProvider) -> None:
    provider._client.chat.return_value = [
        SimpleNamespace(message=SimpleNamespace(content="hel")),
        SimpleNamespace(message=SimpleNamespace(content=None)),
        SimpleNamespace(message=SimpleNamespace(content="lo")),
    ]
    assert list(provider.stream("hi")) == ["hel", "lo"]


def test_stream_raises_provider_error_when_the_server_is_unreachable(provider: OllamaProvider) -> None:
    provider._client.chat.side_effect = ConnectionError("connection refused")
    with pytest.raises(ProviderError):
        list(provider.stream("hi"))


def test_is_available_returns_true_when_the_server_responds(provider: OllamaProvider) -> None:
    provider._client.list.return_value = SimpleNamespace(models=[])
    assert provider.is_available() is True


def test_is_available_returns_false_when_the_server_is_unreachable(provider: OllamaProvider) -> None:
    provider._client.list.side_effect = ConnectionError("connection refused")
    assert provider.is_available() is False
