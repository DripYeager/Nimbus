from __future__ import annotations

from types import SimpleNamespace

import anthropic
import pytest
from pytest_mock import MockerFixture

from core.exceptions import ProviderError
from llm.anthropic_provider import MAX_TOKENS, AnthropicProvider
from models.chat import ChatMessage, TextDelta, ToolCall, ToolSpec

USER_TURN = ChatMessage(role="user", content="find my tax return")
SEARCH_TOOL = ToolSpec(name="search_files", description="Search", parameters={"type": "object"})


@pytest.fixture
def provider(mocker: MockerFixture) -> AnthropicProvider:
    mocker.patch("llm.anthropic_provider.anthropic.Anthropic")
    return AnthropicProvider(api_key="sk-ant-test", model="claude-3-5-haiku-latest")


def _fake_stream(mocker: MockerFixture, text_chunks: list[str]) -> object:
    manager = mocker.MagicMock()
    manager.__enter__.return_value = SimpleNamespace(text_stream=iter(text_chunks))
    return manager


def _fake_chat_stream(mocker: MockerFixture, events: list[object], final_content: list[object]) -> object:
    stream = mocker.MagicMock()
    stream.__iter__.return_value = iter(events)
    stream.get_final_message.return_value = SimpleNamespace(content=final_content)
    manager = mocker.MagicMock()
    manager.__enter__.return_value = stream
    return manager


def _text_event(text: str) -> object:
    return SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="text_delta", text=text))


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


def test_stream_chat_yields_text_deltas_only_for_text(provider: AnthropicProvider, mocker: MockerFixture) -> None:
    events = [
        _text_event("hel"),
        SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="input_json_delta", partial_json="{")),
        SimpleNamespace(type="message_stop"),
        _text_event("lo"),
    ]
    provider._client.messages.stream.return_value = _fake_chat_stream(mocker, events, final_content=[])
    assert list(provider.stream_chat("sys", [USER_TURN], [])) == [TextDelta(text="hel"), TextDelta(text="lo")]


def test_stream_chat_yields_tool_calls_after_the_text(provider: AnthropicProvider, mocker: MockerFixture) -> None:
    tool_block = SimpleNamespace(type="tool_use", id="toolu_1", name="search_files", input={"query": "tax"})
    provider._client.messages.stream.return_value = _fake_chat_stream(
        mocker, [_text_event("Looking.")], final_content=[tool_block]
    )
    assert list(provider.stream_chat("sys", [USER_TURN], [SEARCH_TOOL])) == [
        TextDelta(text="Looking."),
        ToolCall(id="toolu_1", name="search_files", arguments={"query": "tax"}),
    ]


def test_stream_chat_sends_system_and_tools(provider: AnthropicProvider, mocker: MockerFixture) -> None:
    provider._client.messages.stream.return_value = _fake_chat_stream(mocker, [], final_content=[])
    list(provider.stream_chat("sys", [USER_TURN], [SEARCH_TOOL]))
    kwargs = provider._client.messages.stream.call_args.kwargs
    assert kwargs["system"] == "sys"
    assert kwargs["tools"][0]["input_schema"] == SEARCH_TOOL.parameters
    assert kwargs["max_tokens"] == MAX_TOKENS


def test_stream_chat_omits_tools_when_none_are_given(provider: AnthropicProvider, mocker: MockerFixture) -> None:
    provider._client.messages.stream.return_value = _fake_chat_stream(mocker, [], final_content=[])
    list(provider.stream_chat("sys", [USER_TURN], []))
    assert "tools" not in provider._client.messages.stream.call_args.kwargs


def test_stream_chat_raises_provider_error_naming_the_model(provider: AnthropicProvider) -> None:
    provider._client.messages.stream.side_effect = anthropic.AnthropicError("overloaded")
    with pytest.raises(ProviderError, match="claude-3-5-haiku-latest"):
        list(provider.stream_chat("sys", [USER_TURN], []))


def test_list_models_returns_sorted_ids(provider: AnthropicProvider) -> None:
    provider._client.models.list.return_value = [SimpleNamespace(id="claude-b"), SimpleNamespace(id="claude-a")]
    assert provider.list_models() == ["claude-a", "claude-b"]


def test_list_models_raises_provider_error_when_the_request_fails(provider: AnthropicProvider) -> None:
    provider._client.models.list.side_effect = anthropic.AnthropicError("unauthorized")
    with pytest.raises(ProviderError):
        provider.list_models()
