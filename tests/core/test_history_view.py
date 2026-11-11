from __future__ import annotations

from core.history_view import history_turns, step_status
from models.chat import ChatMessage, ShownCode, ToolCall


def _describe(call: ToolCall) -> tuple[str, ShownCode | None]:
    if call.name == "run_command":
        return "Run a PowerShell command", ShownCode(title="PowerShell", text=call.arguments["command"])
    return f"Used {call.name}", None


def _call(call_id: str, name: str, **arguments: str) -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments)


def test_history_turns_merges_one_reply_with_its_steps_and_text() -> None:
    messages = [
        ChatMessage(role="user", content="What's my IP?"),
        ChatMessage(
            role="assistant", content="Let me check.", tool_calls=[_call("a", "run_command", command="ipconfig")]
        ),
        ChatMessage(role="tool", content="IPv4 192.168.1.24", tool_call_id="a", tool_name="run_command"),
        ChatMessage(role="assistant", content="It's 192.168.1.24."),
    ]

    user, reply = history_turns(messages, _describe)

    assert user.text == "What's my IP?"
    assert reply.text == "Let me check.\n\nIt's 192.168.1.24."
    [step] = reply.steps
    assert (step.label, step.status, step.output) == ("Run a PowerShell command", "done", "IPv4 192.168.1.24")
    assert step.code == ShownCode(title="PowerShell", text="ipconfig")


def test_history_turns_leaves_out_a_call_still_waiting() -> None:
    messages = [
        ChatMessage(role="user", content="Delete temp"),
        ChatMessage(role="assistant", tool_calls=[_call("a", "run_command", command="Remove-Item x")]),
    ]

    assert [turn.role for turn in history_turns(messages, _describe)] == ["user"]


def test_history_turns_has_no_output_for_a_declined_step() -> None:
    messages = [
        ChatMessage(role="user", content="Delete temp"),
        ChatMessage(role="assistant", tool_calls=[_call("a", "run_command", command="Remove-Item x")]),
        ChatMessage(role="tool", content="The user declined this action. Don't retry it.", tool_call_id="a"),
    ]

    [step] = history_turns(messages, _describe)[1].steps

    assert (step.status, step.output) == ("denied", None)


def _result(text: str, is_error: bool = False) -> ChatMessage:
    return ChatMessage(role="tool", content=text, tool_call_id="a", is_error=is_error)


def test_step_status_reads_how_a_step_ended() -> None:
    assert step_status("read_file", _result("read_file failed: no such file")) == "failed"
    assert step_status("read_file", _result("read_file hit an unexpected error: KeyError")) == "failed"
    assert step_status("x", _result("Not run: the user sent a new message instead of answering.")) == "denied"
    assert step_status("read_file", _result("Budget: $48,000")) == "done"


def test_step_status_trusts_the_saved_failure_flag() -> None:
    assert step_status("read_file", _result("C:/old.txt no longer exists.", is_error=True)) == "failed"
