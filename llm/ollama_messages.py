"""
Converts the neutral chat shapes in models/chat.py to and from Ollama's chat format.
Does not call the server, ollama_provider.py owns the client and the streaming.
"""

from __future__ import annotations

from typing import Any

from llm.openai_messages import new_tool_call_id, to_openai_tools
from models.chat import ChatMessage, ToolCall, ToolSpec


def to_ollama_messages(system: str, messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """
    Converts a conversation to Ollama's message list, with the system prompt first.

    Ollama has no tool-call ids: an assistant turn's calls carry arguments as a dict, and a tool
    result is matched back by tool_name instead.
    """
    converted: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for message in messages:
        if message.role == "tool":
            converted.append({"role": "tool", "content": message.content, "tool_name": message.tool_name})
        elif message.role == "assistant" and message.tool_calls:
            converted.append(_assistant_with_tool_calls(message))
        else:
            converted.append({"role": message.role, "content": message.content})
    return converted


def to_ollama_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """Converts tool specs to Ollama's tool definitions, which match OpenAI's."""
    return to_openai_tools(tools)


def to_tool_call(ollama_call: Any) -> ToolCall:
    """Converts one of Ollama's streamed tool calls, giving it a fresh id since Ollama sends none."""
    function = ollama_call.function
    return ToolCall(id=new_tool_call_id(), name=function.name, arguments=dict(function.arguments or {}))


def _assistant_with_tool_calls(message: ChatMessage) -> dict[str, Any]:
    """An assistant turn that called tools."""
    return {
        "role": "assistant",
        "content": message.content,
        "tool_calls": [{"function": {"name": call.name, "arguments": call.arguments}} for call in message.tool_calls],
    }
