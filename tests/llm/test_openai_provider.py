from __future__ import annotations

from types import SimpleNamespace

import openai
import pytest
from pytest_mock import MockerFixture

from core.exceptions import ProviderError
from llm.openai_provider import OpenAIProvider
from models.chat import ChatMessage, TextDelta, ToolCall, ToolSpec

USER_TURN = ChatMessage(role="user", content="find my tax return")
SEARCH_TOOL = ToolSpec(name="search_files", description="Search", parameters={"type": "object"})


@pytest.fixture
def provider(mocker: MockerFixture) -> OpenAIProvider:
    mocker.patch("llm.openai_provider.openai.OpenAI")
    return OpenAIProvider(api_key="sk-test", model="gpt-4o-mini")


def _chunk(content: str | None = None, tool_calls: list[object] | None = None) -> object:
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=tool_calls))])


def _tool_delta(
    index: int, call_id: str | None = None, name: str | None = None, arguments: str | None = None
) -> object:
    return SimpleNamespace(index=index, id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


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


def test_stream_chat_yields_text_deltas(provider: OpenAIProvider) -> None:
    provider._client.chat.completions.create.return_value = [_chunk(content="hel"), _chunk(content="lo")]
    assert list(provider.stream_chat("sys", [USER_TURN], [])) == [TextDelta(text="hel"), TextDelta(text="lo")]


def test_stream_chat_skips_chunks_without_choices(provider: OpenAIProvider) -> None:
    provider._client.chat.completions.create.return_value = [_chunk(content="hi"), SimpleNamespace(choices=[])]
    assert list(provider.stream_chat("sys", [USER_TURN], [])) == [TextDelta(text="hi")]


def test_stream_chat_assembles_fragmented_tool_calls(provider: OpenAIProvider) -> None:
    provider._client.chat.completions.create.return_value = [
        _chunk(content="Looking."),
        _chunk(tool_calls=[_tool_delta(0, call_id="call_1", name="search_files", arguments="")]),
        _chunk(tool_calls=[_tool_delta(0, arguments='{"query": ')]),
        _chunk(tool_calls=[_tool_delta(0, arguments='"tax"}')]),
    ]
    assert list(provider.stream_chat("sys", [USER_TURN], [SEARCH_TOOL])) == [
        TextDelta(text="Looking."),
        ToolCall(id="call_1", name="search_files", arguments={"query": "tax"}),
    ]


def test_stream_chat_sends_tools_and_the_system_prompt(provider: OpenAIProvider) -> None:
    provider._client.chat.completions.create.return_value = []
    list(provider.stream_chat("sys", [USER_TURN], [SEARCH_TOOL]))
    kwargs = provider._client.chat.completions.create.call_args.kwargs
    assert kwargs["messages"][0] == {"role": "system", "content": "sys"}
    assert kwargs["tools"][0]["function"]["name"] == "search_files"
    assert kwargs["stream"] is True


def test_stream_chat_omits_tools_when_none_are_given(provider: OpenAIProvider) -> None:
    provider._client.chat.completions.create.return_value = []
    list(provider.stream_chat("sys", [USER_TURN], []))
    assert "tools" not in provider._client.chat.completions.create.call_args.kwargs


def test_stream_chat_raises_provider_error_naming_the_model(provider: OpenAIProvider) -> None:
    provider._client.chat.completions.create.side_effect = openai.OpenAIError("rate limited")
    with pytest.raises(ProviderError, match="gpt-4o-mini"):
        list(provider.stream_chat("sys", [USER_TURN], []))


def test_stream_chat_raises_provider_error_on_malformed_tool_arguments(provider: OpenAIProvider) -> None:
    provider._client.chat.completions.create.return_value = [
        _chunk(tool_calls=[_tool_delta(0, call_id="call_1", name="search_files", arguments='{"query": ')]),
    ]
    with pytest.raises(ProviderError):
        list(provider.stream_chat("sys", [USER_TURN], [SEARCH_TOOL]))


def test_list_models_keeps_only_chat_models_on_openai(provider: OpenAIProvider) -> None:
    ids = ["text-embedding-3-small", "gpt-5-mini", "o3-mini", "dall-e-3", "chatgpt-4o-latest", "gpt-4o"]
    provider._client.models.list.return_value = [SimpleNamespace(id=model_id) for model_id in ids]
    assert provider.list_models() == ["chatgpt-4o-latest", "gpt-4o", "gpt-5-mini", "o3-mini"]


def test_list_models_returns_every_id_from_a_compatible_server(mocker: MockerFixture) -> None:
    mocker.patch("llm.openai_provider.openai.OpenAI")
    provider = OpenAIProvider(api_key="not-needed", model="qwen", base_url="http://localhost:1234/v1")
    provider._client.models.list.return_value = [SimpleNamespace(id="qwen"), SimpleNamespace(id="deepseek-v3")]
    assert provider.list_models() == ["deepseek-v3", "qwen"]


def test_list_models_raises_provider_error_when_the_request_fails(provider: OpenAIProvider) -> None:
    provider._client.models.list.side_effect = openai.OpenAIError("unauthorized")
    with pytest.raises(ProviderError):
        provider.list_models()


def test_provider_builds_before_a_key_has_been_saved(mocker: MockerFixture) -> None:
    client_cls = mocker.patch("llm.openai_provider.openai.OpenAI")

    OpenAIProvider(api_key=None, model="gpt-5-mini")

    assert client_cls.call_args.kwargs["api_key"]
