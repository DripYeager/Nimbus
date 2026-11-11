"""Fakes and helpers shared by the Agent tests (fixtures live in conftest.py)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from core.agent import (
    Agent,
)
from models.chat import (
    ChatEvent,
    ChatMessage,
    ChatToken,
    TextDelta,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from tools.registry import ToolRegistry, object_schema

Turn = list[TextDelta | ToolCall] | Exception


class ScriptedProvider:
    """Plays back one scripted model response per stream_chat call, and remembers what it saw."""

    def __init__(self, turns: list[Turn]) -> None:
        self._turns = list(turns)
        self.seen: list[list[ChatMessage]] = []
        self.tools_seen: list[list[ToolSpec]] = []

    def stream_chat(self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]) -> Iterator[Any]:
        self.seen.append(list(messages))
        self.tools_seen.append(list(tools))
        turn = self._turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        yield from turn


class RecordingTool:
    """A tool handler that returns a fixed result and counts how often it ran."""

    def __init__(self, result: ToolResult) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def __call__(self, args: dict[str, Any]) -> ToolResult:
        self.calls.append(args)
        return self.result


def simple_spec(name: str) -> ToolSpec:
    return ToolSpec(name=name, description=name, parameters=object_schema({}))


def make_agent(provider: ScriptedProvider, registry: ToolRegistry, fallback: Any = None) -> Agent:
    return Agent(provider, registry, lambda: "system prompt", fallback or (lambda question: (iter([]), [])))


def make_call(name: str, call_id: str = "c1", **arguments: Any) -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments)


def user_turn(text: str = "hi") -> list[ChatMessage]:
    return [ChatMessage(role="user", content=text)]


def tokens_of(events: list[ChatEvent]) -> str:
    return "".join(e.text for e in events if isinstance(e, ChatToken))


def paused_history(*calls: ToolCall) -> list[ChatMessage]:
    return [*user_turn("open it"), ChatMessage(role="assistant", tool_calls=list(calls))]
