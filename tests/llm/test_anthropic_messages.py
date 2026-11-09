from __future__ import annotations

from types import SimpleNamespace

from llm.anthropic_messages import to_anthropic_messages, to_anthropic_tools, tool_calls_from_message
from models.chat import ChatMessage, ToolCall, ToolSpec


def _tool_result(call_id: str, content: str) -> ChatMessage:
    return ChatMessage(role="tool", content=content, tool_call_id=call_id, tool_name="search_files")


def test_to_anthropic_messages_keeps_plain_turns_as_strings() -> None:
    messages = [ChatMessage(role="user", content="hi"), ChatMessage(role="assistant", content="hello")]
    assert to_anthropic_messages(messages) == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_to_anthropic_messages_turns_tool_calls_into_text_and_tool_use_blocks() -> None:
    call = ToolCall(id="toolu_1", name="search_files", arguments={"query": "tax"})
    converted = to_anthropic_messages([ChatMessage(role="assistant", content="Looking.", tool_calls=[call])])
    assert converted == [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Looking."},
                {"type": "tool_use", "id": "toolu_1", "name": "search_files", "input": {"query": "tax"}},
            ],
        }
    ]


def test_to_anthropic_messages_omits_the_text_block_when_the_tool_turn_has_no_text() -> None:
    call = ToolCall(id="toolu_1", name="search_files")
    converted = to_anthropic_messages([ChatMessage(role="assistant", tool_calls=[call])])
    assert [block["type"] for block in converted[0]["content"]] == ["tool_use"]


def test_to_anthropic_messages_merges_consecutive_tool_results_into_one_user_turn() -> None:
    converted = to_anthropic_messages([_tool_result("toolu_1", "a"), _tool_result("toolu_2", "b")])
    assert converted == [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "a"},
                {"type": "tool_result", "tool_use_id": "toolu_2", "content": "b"},
            ],
        }
    ]


def test_to_anthropic_messages_does_not_merge_a_tool_result_into_a_plain_user_turn() -> None:
    converted = to_anthropic_messages([ChatMessage(role="user", content="hi"), _tool_result("toolu_1", "a")])
    assert len(converted) == 2


def test_to_anthropic_tools_uses_input_schema() -> None:
    spec = ToolSpec(name="search_files", description="Search", parameters={"type": "object"})
    assert to_anthropic_tools([spec]) == [
        {"name": "search_files", "description": "Search", "input_schema": {"type": "object"}}
    ]


def test_tool_calls_from_message_keeps_only_tool_use_blocks() -> None:
    message = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="Looking."),
            SimpleNamespace(type="tool_use", id="toolu_1", name="search_files", input={"query": "tax"}),
        ]
    )
    assert tool_calls_from_message(message) == [ToolCall(id="toolu_1", name="search_files", arguments={"query": "tax"})]


def test_to_anthropic_messages_drops_an_empty_assistant_turn() -> None:
    messages = [
        ChatMessage(role="user", content="hi"),
        ChatMessage(role="assistant", content=""),
        ChatMessage(role="user", content="still there?"),
    ]

    converted = to_anthropic_messages(messages)

    assert [m["role"] for m in converted] == ["user", "user"]
