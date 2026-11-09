from __future__ import annotations

from config.settings import get_settings
from core.agent import (
    DECLINED_MESSAGE,
)
from models.chat import (
    ChatMessage,
    ConfirmationNeeded,
    ConfirmRequest,
    TextDelta,
    ToolActivity,
)
from tests.core.agent_test_support import (
    RecordingTool,
    ScriptedProvider,
    make_agent,
    make_call,
    paused_history,
    tokens_of,
    user_turn,
)
from tools.registry import ToolRegistry


def test_run_pauses_before_an_action_tool(registry: ToolRegistry, launch: RecordingTool) -> None:
    provider = ScriptedProvider([[make_call("launch")]])

    events = list(make_agent(provider, registry).run(user_turn()))

    assert events[-1] == ConfirmationNeeded(call_id="c1", tool="launch", description="Launch the thing")
    assert launch.calls == []


def test_run_skips_confirmation_for_an_auto_approved_tool(registry: ToolRegistry, launch: RecordingTool) -> None:
    get_settings().auto_approved_tools = ["launch"]
    provider = ScriptedProvider([[make_call("launch")], [TextDelta(text="Opened.")]])

    events = list(make_agent(provider, registry).run(user_turn()))

    assert launch.calls == [{}]
    assert not any(isinstance(e, ConfirmationNeeded) for e in events)


def test_run_executes_an_approved_call_and_continues(registry: ToolRegistry, launch: RecordingTool) -> None:
    provider = ScriptedProvider([[TextDelta(text="Opened it.")]])
    messages = paused_history(make_call("launch"))

    events = list(make_agent(provider, registry).run(messages, ConfirmRequest(call_id="c1", approved=True)))

    assert launch.calls == [{}]
    assert messages[2].content == "launched"
    assert tokens_of(events) == "Opened it."


def test_run_records_a_declined_call_and_continues(registry: ToolRegistry, launch: RecordingTool) -> None:
    provider = ScriptedProvider([[TextDelta(text="Okay, I won't.")]])
    messages = paused_history(make_call("launch"))

    events = list(make_agent(provider, registry).run(messages, ConfirmRequest(call_id="c1", approved=False)))

    assert launch.calls == []
    assert messages[2].content == DECLINED_MESSAGE
    assert [e.status for e in events if isinstance(e, ToolActivity)] == ["denied"]


def test_run_runs_earlier_calls_before_pausing_on_a_later_action(
    registry: ToolRegistry, lookup: RecordingTool, launch: RecordingTool
) -> None:
    provider = ScriptedProvider([[make_call("lookup", "c1"), make_call("launch", "c2")]])
    messages = user_turn()

    events = list(make_agent(provider, registry).run(messages))

    assert len(lookup.calls) == 1
    assert launch.calls == []
    assert [e.call_id for e in events if isinstance(e, ConfirmationNeeded)] == ["c2"]
    assert [m.role for m in messages] == ["user", "assistant", "tool"]


def test_run_resumes_the_second_call_of_a_turn_after_approval(registry: ToolRegistry, launch: RecordingTool) -> None:
    messages = [
        *paused_history(make_call("lookup", "c1"), make_call("launch", "c2")),
        ChatMessage(role="tool", content="found it", tool_call_id="c1", tool_name="lookup"),
    ]
    provider = ScriptedProvider([[TextDelta(text="All done.")]])

    list(make_agent(provider, registry).run(messages, ConfirmRequest(call_id="c2", approved=True)))

    assert launch.calls == [{}]
    assert [m.tool_call_id for m in messages if m.role == "tool"] == ["c1", "c2"]
