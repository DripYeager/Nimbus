"""
Converts the neutral chat shapes in models/chat.py to and from OpenAI's chat-completions format,
including reassembling tool calls that arrive in fragments while streaming.
Does not call the API — openai_provider.py owns the client and the streaming loop.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from core.exceptions import ProviderError
from models.chat import ChatMessage, ToolCall, ToolSpec

# Index of a streamed tool call -> its id, name and the arguments JSON received so far.
ToolCallFragments = dict[int, dict[str, str]]


def new_tool_call_id() -> str:
    """An id for a tool call the API didn't name, so its result can still be matched back to it."""
    return f"call_{uuid.uuid4().hex}"


def to_openai_messages(system: str, messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """Converts a conversation to OpenAI's message list, with the system prompt first."""
    converted: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for message in messages:
        if message.role == "tool":
            converted.append({"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content})
        elif message.role == "assistant" and message.tool_calls:
            converted.append(_assistant_with_tool_calls(message))
        else:
            converted.append({"role": message.role, "content": message.content})
    return converted


def to_openai_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """Converts tool specs to OpenAI's function-tool definitions (Ollama accepts the same shape)."""
    return [
        {
            "type": "function",
            "function": {"name": tool.name, "description": tool.description, "parameters": tool.parameters},
        }
        for tool in tools
    ]


def add_tool_call_fragments(fragments: ToolCallFragments, deltas: list[Any]) -> None:
    """
    Folds one chunk's tool-call deltas into the running fragments.

    The id and name arrive in the first delta for a call; the arguments JSON then trickles in as
    string pieces across later deltas that carry only the call's index.
    """
    for delta in deltas:
        fragment = fragments.setdefault(delta.index, {"id": "", "name": "", "arguments": ""})
        if delta.id:
            fragment["id"] = delta.id
        function = delta.function
        if function is None:
            continue
        if function.name:
            fragment["name"] += function.name
        if function.arguments:
            fragment["arguments"] += function.arguments


def finish_tool_calls(fragments: ToolCallFragments) -> list[ToolCall]:
    """Turns fully streamed fragments into tool calls, in the order the model made them."""
    return [_parse_fragment(fragments[index]) for index in sorted(fragments)]


def _parse_fragment(fragment: dict[str, str]) -> ToolCall:
    """Parses one fragment's arguments JSON; raises ProviderError if the model sent malformed JSON."""
    raw_arguments = fragment["arguments"].strip()
    try:
        arguments = json.loads(raw_arguments) if raw_arguments else {}
    except json.JSONDecodeError as e:
        raise ProviderError(
            f"The model called tool '{fragment['name']}' with arguments that aren't valid JSON: {e}. "
            "Try again, or pick a model with more reliable tool calling."
        ) from e
    if not isinstance(arguments, dict):
        raise ProviderError(f"The model called tool '{fragment['name']}' with non-object arguments: {raw_arguments}")
    return ToolCall(id=fragment["id"] or new_tool_call_id(), name=fragment["name"], arguments=arguments)


def _assistant_with_tool_calls(message: ChatMessage) -> dict[str, Any]:
    """An assistant turn that called tools, with each call's arguments re-encoded as JSON."""
    return {
        "role": "assistant",
        "content": message.content or None,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ],
    }
