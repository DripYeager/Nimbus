from __future__ import annotations

from types import SimpleNamespace

import ollama
import pytest
from pytest_mock import MockerFixture

from core.exceptions import ProviderError, ToolsUnsupportedError
from llm.ollama_provider import OllamaProvider
from models.chat import ChatMessage, TextDelta, ToolCall, ToolSpec

USER_TURN = ChatMessage(role="user", content="find my tax return")
SEARCH_TOOL = ToolSpec(name="search_files", description="Search", parameters={"type": "object"})


@pytest.fixture
def provider(mocker: MockerFixture) -> OllamaProvider:
    mocker.patch("llm.ollama_provider.ollama.Client")
    return OllamaProvider(host="http://localhost:11434", model="llama3.1:8b")


def _chunk(content: str = "", tool_calls: list[object] | None = None) -> object:
    return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))


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


def test_stream_chat_yields_text_deltas(provider: OllamaProvider) -> None:
    provider._client.chat.return_value = [_chunk(content="hel"), _chunk(content=""), _chunk(content="lo")]
    assert list(provider.stream_chat("sys", [USER_TURN], [])) == [TextDelta(text="hel"), TextDelta(text="lo")]


def test_stream_chat_yields_a_tool_call_with_a_generated_id(provider: OllamaProvider) -> None:
    call = SimpleNamespace(function=SimpleNamespace(name="search_files", arguments={"query": "tax"}))
    provider._client.chat.return_value = [_chunk(tool_calls=[call])]
    (tool_call,) = list(provider.stream_chat("sys", [USER_TURN], [SEARCH_TOOL]))
    assert isinstance(tool_call, ToolCall)
    assert tool_call.id.startswith("call_")
    assert (tool_call.name, tool_call.arguments) == ("search_files", {"query": "tax"})


def test_stream_chat_sends_tools_and_the_system_prompt(provider: OllamaProvider) -> None:
    provider._client.chat.return_value = []
    list(provider.stream_chat("sys", [USER_TURN], [SEARCH_TOOL]))
    kwargs = provider._client.chat.call_args.kwargs
    assert kwargs["messages"][0] == {"role": "system", "content": "sys"}
    assert kwargs["tools"][0]["function"]["name"] == "search_files"
    assert kwargs["stream"] is True


def test_stream_chat_omits_tools_when_none_are_given(provider: OllamaProvider) -> None:
    provider._client.chat.return_value = []
    list(provider.stream_chat("sys", [USER_TURN], []))
    assert "tools" not in provider._client.chat.call_args.kwargs


def test_stream_chat_raises_tools_unsupported_for_a_model_without_tools(provider: OllamaProvider) -> None:
    provider._client.chat.side_effect = ollama.ResponseError("registry/gemma3 does not support tools", 400)
    with pytest.raises(ToolsUnsupportedError):
        list(provider.stream_chat("sys", [USER_TURN], [SEARCH_TOOL]))


def test_stream_chat_raises_provider_error_naming_the_model(provider: OllamaProvider) -> None:
    provider._client.chat.side_effect = ConnectionError("connection refused")
    with pytest.raises(ProviderError, match="llama3.1:8b") as caught:
        list(provider.stream_chat("sys", [USER_TURN], []))
    assert not isinstance(caught.value, ToolsUnsupportedError)


def test_list_models_returns_sorted_names(provider: OllamaProvider) -> None:
    provider._client.list.return_value = SimpleNamespace(
        models=[SimpleNamespace(model="qwen2.5:7b"), SimpleNamespace(model=None), SimpleNamespace(model="gemma3:4b")]
    )
    assert provider.list_models() == ["gemma3:4b", "qwen2.5:7b"]


def test_list_models_raises_provider_error_when_the_server_is_unreachable(provider: OllamaProvider) -> None:
    provider._client.list.side_effect = ConnectionError("connection refused")
    with pytest.raises(ProviderError):
        provider.list_models()
