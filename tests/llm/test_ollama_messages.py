from __future__ import annotations

from types import SimpleNamespace

from llm.ollama_messages import to_ollama_messages, to_ollama_tools, to_tool_call
from models.chat import ChatMessage, ToolCall, ToolSpec


def test_to_ollama_messages_puts_the_system_prompt_first() -> None:
    converted = to_ollama_messages("be brief", [ChatMessage(role="user", content="hi")])
    assert converted == [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}]


def test_to_ollama_messages_keeps_tool_call_arguments_as_a_dict() -> None:
    call = ToolCall(id="call_1", name="search_files", arguments={"query": "tax"})
    converted = to_ollama_messages("", [ChatMessage(role="assistant", content="Looking.", tool_calls=[call])])
    assert converted[1] == {
        "role": "assistant",
        "content": "Looking.",
        "tool_calls": [{"function": {"name": "search_files", "arguments": {"query": "tax"}}}],
    }


def test_to_ollama_messages_matches_a_tool_result_by_tool_name() -> None:
    message = ChatMessage(role="tool", content="found 3", tool_call_id="call_1", tool_name="search_files")
    assert to_ollama_messages("", [message])[1] == {"role": "tool", "content": "found 3", "tool_name": "search_files"}


def test_to_ollama_tools_uses_the_function_tool_shape() -> None:
    spec = ToolSpec(name="search_files", description="Search", parameters={"type": "object"})
    assert to_ollama_tools([spec])[0]["function"]["name"] == "search_files"


def test_to_tool_call_generates_an_id_and_copies_the_arguments() -> None:
    ollama_call = SimpleNamespace(function=SimpleNamespace(name="search_files", arguments={"query": "tax"}))
    call = to_tool_call(ollama_call)
    assert call.id.startswith("call_")
    assert (call.name, call.arguments) == ("search_files", {"query": "tax"})
