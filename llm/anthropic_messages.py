"""
Converts the neutral chat shapes in models/chat.py to and from Anthropic's Messages API format.
Does not call the API, anthropic_provider.py owns the client and the streaming.
"""

from __future__ import annotations

from typing import Any

from models.chat import ChatMessage, ToolCall, ToolSpec


def to_anthropic_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """
    Converts a conversation to Anthropic's message list.

    Anthropic has no "tool" role: tool results are tool_result blocks inside a user turn, and
    every result answering the same assistant turn must share one user message, so runs of
    consecutive tool messages are merged.

    Args:
        messages: The conversation so far, oldest first. The system prompt is not part of it.

    Returns:
        Message dicts ready for the `messages=` parameter.
    """
    converted: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "tool":
            _append_tool_result(converted, message)
        elif message.role == "assistant":
            # The API rejects an empty assistant turn, and the model does occasionally end a turn
            # with no text, replaying that one would break every later message in the chat.
            if message.content or message.tool_calls:
                converted.append({"role": "assistant", "content": _assistant_content(message)})
        else:
            converted.append({"role": "user", "content": message.content})
    return converted


def to_anthropic_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """Converts tool specs to Anthropic's tool definitions."""
    return [{"name": tool.name, "description": tool.description, "input_schema": tool.parameters} for tool in tools]


def tool_calls_from_message(message: Any) -> list[ToolCall]:
    """Pulls the tool_use blocks out of a finished Anthropic message."""
    return [
        ToolCall(id=block.id, name=block.name, arguments=dict(block.input or {}))
        for block in message.content
        if block.type == "tool_use"
    ]


def _assistant_content(message: ChatMessage) -> str | list[dict[str, Any]]:
    """Plain text for an ordinary reply; text plus tool_use blocks when the turn called tools."""
    if not message.tool_calls:
        return message.content
    blocks: list[dict[str, Any]] = []
    if message.content:
        blocks.append({"type": "text", "text": message.content})
    blocks.extend(
        {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments} for call in message.tool_calls
    )
    return blocks


def _append_tool_result(converted: list[dict[str, Any]], message: ChatMessage) -> None:
    """Adds a tool result, joining the previous user turn if that turn is itself tool results."""
    block = {"type": "tool_result", "tool_use_id": message.tool_call_id, "content": message.content}
    previous = converted[-1] if converted else None
    # Plain user turns are strings, so a list-content user turn can only be a run of tool results.
    if previous and previous["role"] == "user" and isinstance(previous["content"], list):
        previous["content"].append(block)
    else:
        converted.append({"role": "user", "content": [block]})
