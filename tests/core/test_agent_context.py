from __future__ import annotations

from datetime import datetime

from core.agent import CONTEXT_MESSAGES, TRIM_STEP, _model_view, with_time
from models.chat import ChatMessage


def _chat(turns: int) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    for i in range(turns):
        messages += [ChatMessage(role="user", content=f"q{i}"), ChatMessage(role="assistant", content=f"a{i}")]
    return messages


def test_with_time_notes_the_time_on_the_latest_user_message_only() -> None:
    messages = [*_chat(2), ChatMessage(role="user", content="what time is it?")]

    seen = with_time(messages, datetime(2026, 11, 11, 16, 42))

    assert seen[-1].content == "what time is it?\n\n(Local time now: 16:42)"
    assert seen[:-1] == messages[:-1]
    assert messages[-1].content == "what time is it?"


def test_with_time_without_a_user_message_changes_nothing() -> None:
    messages = [ChatMessage(role="assistant", content="hi")]

    assert with_time(messages, datetime(2026, 11, 11, 9, 0)) == messages


def test_model_view_keeps_the_same_start_for_several_turns() -> None:
    """The cut moves in steps, so the start of what the model sees (and could cache) holds."""
    first_cuts = set()
    for turns in range(CONTEXT_MESSAGES // 2 + 1, CONTEXT_MESSAGES // 2 + TRIM_STEP // 2):
        first_cuts.add(_model_view(_chat(turns))[0].content)

    assert len(first_cuts) == 1
