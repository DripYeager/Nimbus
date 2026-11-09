from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.exceptions import ProviderError
from llm.openai_messages import (
    ToolCallFragments,
    add_tool_call_fragments,
    finish_tool_calls,
    new_tool_call_id,
    to_openai_messages,
    to_openai_tools,
)
from models.chat import ChatMessage, ToolCall, ToolSpec


def _delta(index: int, call_id: str | None = None, name: str | None = None, arguments: str | None = None) -> object:
    return SimpleNamespace(index=index, id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


def test_new_tool_call_id_is_prefixed_and_unique() -> None:
    first, second = new_tool_call_id(), new_tool_call_id()
    assert first.startswith("call_") and first != second


def test_to_openai_messages_puts_the_system_prompt_first() -> None:
    converted = to_openai_messages("be brief", [ChatMessage(role="user", content="hi")])
    assert converted == [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}]


def test_to_openai_messages_encodes_tool_call_arguments_as_json() -> None:
    call = ToolCall(id="call_1", name="search_files", arguments={"query": "tax"})
    converted = to_openai_messages("", [ChatMessage(role="assistant", tool_calls=[call])])
    assert converted[1] == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "search_files", "arguments": '{"query": "tax"}'}}
        ],
    }


def test_to_openai_messages_converts_a_tool_result() -> None:
    message = ChatMessage(role="tool", content="found 3", tool_call_id="call_1", tool_name="search_files")
    assert to_openai_messages("", [message])[1] == {"role": "tool", "tool_call_id": "call_1", "content": "found 3"}


def test_to_openai_tools_wraps_each_spec_as_a_function() -> None:
    spec = ToolSpec(name="search_files", description="Search", parameters={"type": "object"})
    assert to_openai_tools([spec]) == [
        {
            "type": "function",
            "function": {"name": "search_files", "description": "Search", "parameters": {"type": "object"}},
        }
    ]


def test_add_tool_call_fragments_joins_argument_pieces_by_index() -> None:
    fragments: ToolCallFragments = {}
    add_tool_call_fragments(fragments, [_delta(0, "call_1", "search_files", '{"qu')])
    add_tool_call_fragments(fragments, [_delta(0, arguments='ery": "tax"}')])
    assert fragments == {0: {"id": "call_1", "name": "search_files", "arguments": '{"query": "tax"}'}}


def test_add_tool_call_fragments_skips_deltas_without_a_function() -> None:
    fragments: ToolCallFragments = {}
    add_tool_call_fragments(fragments, [SimpleNamespace(index=0, id="call_1", function=None)])
    assert fragments == {0: {"id": "call_1", "name": "", "arguments": ""}}


def test_finish_tool_calls_parses_arguments_in_index_order() -> None:
    fragments: ToolCallFragments = {
        1: {"id": "call_2", "name": "open_file", "arguments": '{"path": "a.txt"}'},
        0: {"id": "call_1", "name": "search_files", "arguments": ""},
    }
    assert finish_tool_calls(fragments) == [
        ToolCall(id="call_1", name="search_files", arguments={}),
        ToolCall(id="call_2", name="open_file", arguments={"path": "a.txt"}),
    ]


def test_finish_tool_calls_generates_an_id_when_the_server_sent_none() -> None:
    calls = finish_tool_calls({0: {"id": "", "name": "search_files", "arguments": "{}"}})
    assert calls[0].id.startswith("call_")


def test_finish_tool_calls_raises_provider_error_on_invalid_json() -> None:
    with pytest.raises(ProviderError, match="search_files"):
        finish_tool_calls({0: {"id": "call_1", "name": "search_files", "arguments": '{"query": '}})


def test_finish_tool_calls_raises_provider_error_on_non_object_arguments() -> None:
    with pytest.raises(ProviderError):
        finish_tool_calls({0: {"id": "call_1", "name": "search_files", "arguments": "[1, 2]"}})
