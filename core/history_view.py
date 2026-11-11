"""
Turns a saved conversation into what the chat shows when it's reopened: the user's messages, and
each reply as one unit with its tool steps (label, outcome, and for code and commands the code
and the start of its output), the way it looked live. Owns that mapping only; labels and code
come from the tool registry, storage from core/conversation_store.py.
"""

from __future__ import annotations

from collections.abc import Callable

from models.chat import ChatMessage, HistoryStep, HistoryTurn, ShownCode, ToolCall

# (call) -> (step label, the code it runs or None)
StepDescriber = Callable[[ToolCall], tuple[str, ShownCode | None]]
# Results that mean the step didn't run: the user said no, or moved on without answering.
NOT_RUN_PREFIXES = ("The user declined this action", "Not run: the user sent a new message")
SHOWN_OUTPUT_CHARS = 4000
PARAGRAPH = "\n\n"


def history_turns(messages: list[ChatMessage], describe: StepDescriber) -> list[HistoryTurn]:
    """The conversation as turns; a call still waiting for an answer has no step yet."""
    results = {m.tool_call_id: m for m in messages if m.role == "tool" and m.tool_call_id}
    turns: list[HistoryTurn] = []
    for message in messages:
        if message.role == "user":
            turns.append(HistoryTurn(role="user", text=message.content))
        elif message.role == "assistant":
            reply = _current_reply(turns)
            if message.content.strip():
                reply.text = f"{reply.text}{PARAGRAPH}{message.content}" if reply.text else message.content
            reply.steps.extend(
                _step(call, results[call.id], describe) for call in message.tool_calls if call.id in results
            )
    return [turn for turn in turns if turn.role == "user" or turn.text.strip() or turn.steps]


def step_status(tool: str, result: ChatMessage) -> str:
    """How a saved step ended: the failure flag saved with the result, or for chats saved
    before there was one, the result's wording."""
    text = result.content
    if text.startswith(NOT_RUN_PREFIXES):
        return "denied"
    if result.is_error or text.startswith((f"{tool} failed:", f"{tool} hit an unexpected error")):
        return "failed"
    return "done"


def _current_reply(turns: list[HistoryTurn]) -> HistoryTurn:
    """The reply being built: messages after one user message belong to one reply."""
    if not turns or turns[-1].role == "user":
        turns.append(HistoryTurn(role="assistant"))
    return turns[-1]


def _step(call: ToolCall, result: ChatMessage, describe: StepDescriber) -> HistoryStep:
    label, code = describe(call)
    status = step_status(call.name, result)
    output = result.content[:SHOWN_OUTPUT_CHARS] if code is not None and status != "denied" else None
    return HistoryStep(call_id=call.id, label=label, status=status, code=code, output=output)
