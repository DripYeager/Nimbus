from __future__ import annotations

import pytest

from config.settings import get_settings
from core.agent import SHOWN_OUTPUT_CHARS
from models.chat import ConfirmationNeeded, ConfirmRequest, ShownCode, TextDelta, ToolActivity, ToolResult
from tests.core.agent_test_support import (
    RecordingTool,
    ScriptedProvider,
    make_agent,
    make_call,
    paused_history,
    simple_spec,
    user_turn,
)
from tools.registry import Tool, ToolRegistry


def _code_registry(tool: RecordingTool, skippable: bool = True) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            simple_spec("run_python"),
            tool,
            lambda a: "Run Python code",
            requires_confirmation=True,
            always_allowable=False,
            can_skip_in_settings=skippable,
            show_code=lambda a: ShownCode(title="Python", text=a["code"]),
        )
    )
    return registry


@pytest.fixture
def printer() -> RecordingTool:
    return RecordingTool(ToolResult(content="6\n"))


def test_run_card_carries_the_code(printer: RecordingTool) -> None:
    provider = ScriptedProvider([[make_call("run_python", code="print(1 + 5)")]])

    events = list(make_agent(provider, _code_registry(printer)).run(user_turn()))

    [card] = [e for e in events if isinstance(e, ConfirmationNeeded)]
    assert card.code == ShownCode(title="Python", text="print(1 + 5)")
    assert card.description == "Run Python code"


def test_run_steps_carry_the_code_and_then_the_output(printer: RecordingTool, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "auto_approved_tools", ["run_python"])
    provider = ScriptedProvider([[make_call("run_python", code="print(1 + 5)")], [TextDelta(text="It's 6.")]])

    events = list(make_agent(provider, _code_registry(printer)).run(user_turn()))

    running, done = [e for e in events if isinstance(e, ToolActivity)]
    assert running.code is not None and running.output is None
    assert done.status == "done" and done.output == "6\n"


def test_run_skips_the_card_when_settings_allow_code(printer: RecordingTool, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "auto_approved_tools", ["run_python"])
    provider = ScriptedProvider([[make_call("run_python", code="print(1)")], [TextDelta(text="Done.")]])

    events = list(make_agent(provider, _code_registry(printer)).run(user_turn()))

    assert not any(isinstance(e, ConfirmationNeeded) for e in events)
    assert printer.calls


def test_run_still_asks_when_the_tool_cant_be_skipped(printer: RecordingTool, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "auto_approved_tools", ["run_python"])
    provider = ScriptedProvider([[make_call("run_python", code="print(1)")]])

    events = list(make_agent(provider, _code_registry(printer, skippable=False)).run(user_turn()))

    assert any(isinstance(e, ConfirmationNeeded) for e in events)


def test_run_trims_long_output_for_the_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "auto_approved_tools", ["run_python"])
    noisy = RecordingTool(ToolResult(content="x" * (SHOWN_OUTPUT_CHARS + 500)))
    provider = ScriptedProvider([[make_call("run_python", code="print('x' * 9999)")], [TextDelta(text="Done.")]])

    events = list(make_agent(provider, _code_registry(noisy)).run(user_turn()))

    done = [e for e in events if isinstance(e, ToolActivity)][-1]
    assert len(done.output or "") == SHOWN_OUTPUT_CHARS


def test_run_approved_call_shows_its_output(printer: RecordingTool) -> None:
    call = make_call("run_python", code="print(1 + 5)")
    provider = ScriptedProvider([[TextDelta(text="It's 6.")]])

    events = list(
        make_agent(provider, _code_registry(printer)).run(
            paused_history(call), ConfirmRequest(call_id="c1", approved=True)
        )
    )

    done = [e for e in events if isinstance(e, ToolActivity)][-1]
    assert done.output == "6\n"


def test_registry_code_for_other_tools_is_none(printer: RecordingTool) -> None:
    registry = _code_registry(printer)
    registry.register(Tool(simple_spec("search_files"), printer, lambda a: "Search"))

    assert registry.code_for(make_call("search_files", query="x")) is None
    assert registry.code_for(make_call("ghost")) is None
