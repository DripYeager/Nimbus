from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from config.settings import get_settings
from core.agent import (
    CONTEXT_MESSAGES,
    EMPTY_ANSWER_MESSAGE,
    MAX_TOOL_RESULT_CHARS,
    STEP_LIMIT_MESSAGE,
    SourceTracker,
    pending_tool_calls,
)
from core.attachment_format import with_attachment
from core.exceptions import ProviderError, ToolsUnsupportedError
from models.chat import (
    ChatMessage,
    ChatSources,
    ConfirmRequest,
    TextDelta,
    ToolActivity,
    ToolResult,
    ToolSpec,
)
from models.schema import SourceRef
from tests.core.agent_test_support import (
    RecordingTool,
    ScriptedProvider,
    make_agent,
    make_call,
    paused_history,
    simple_spec,
    tokens_of,
    user_turn,
)
from tools.registry import Tool, ToolRegistry


def test_run_streams_text_tokens_for_a_plain_answer(registry: ToolRegistry) -> None:
    provider = ScriptedProvider([[TextDelta(text="Hel"), TextDelta(text="lo")]])
    messages = user_turn()

    events = list(make_agent(provider, registry).run(messages))

    assert tokens_of(events) == "Hello"
    assert messages[-1] == ChatMessage(role="assistant", content="Hello")


def test_run_executes_tool_calls_and_loops_until_an_answer(registry: ToolRegistry, lookup: RecordingTool) -> None:
    provider = ScriptedProvider(
        [[TextDelta(text="Let me look. "), make_call("lookup", q="x")], [TextDelta(text="Done.")]]
    )
    messages = user_turn()

    events = list(make_agent(provider, registry).run(messages))

    assert lookup.calls == [{"q": "x"}]
    assert [m.role for m in messages] == ["user", "assistant", "tool", "assistant"]
    assert tokens_of(events) == "Let me look. Done."


def test_run_reports_running_then_done_activity_for_a_tool(registry: ToolRegistry) -> None:
    provider = ScriptedProvider([[make_call("lookup")], [TextDelta(text="ok")]])

    events = list(make_agent(provider, registry).run(user_turn()))

    statuses = [e.status for e in events if isinstance(e, ToolActivity)]
    assert statuses == ["running", "done"]


def test_run_reports_failed_activity_for_an_unknown_tool(registry: ToolRegistry) -> None:
    provider = ScriptedProvider([[make_call("no_such_tool")], [TextDelta(text="sorry")]])
    messages = user_turn()

    events = list(make_agent(provider, registry).run(messages))

    assert [e.status for e in events if isinstance(e, ToolActivity)][-1] == "failed"
    assert "no tool called" in messages[2].content


def test_run_feeds_tool_results_back_to_the_model(registry: ToolRegistry) -> None:
    provider = ScriptedProvider([[make_call("lookup")], [TextDelta(text="ok")]])

    list(make_agent(provider, registry).run(user_turn()))

    second_view = provider.seen[1]
    assert second_view[-1] == ChatMessage(role="tool", content="found it", tool_call_id="c1", tool_name="lookup")


def test_run_stops_with_a_message_after_max_agent_steps(registry: ToolRegistry) -> None:
    get_settings().max_agent_steps = 2
    provider = ScriptedProvider([[make_call("lookup", "c1")], [make_call("lookup", "c2")], [TextDelta(text="never")]])

    events = list(make_agent(provider, registry).run(user_turn()))

    assert len(provider.seen) == 2
    assert tokens_of(events) == STEP_LIMIT_MESSAGE


def test_run_falls_back_to_retrieval_when_the_first_turn_lacks_tool_support(registry: ToolRegistry) -> None:
    source = SourceRef(file_name="notes.txt", file_path="C:/notes.txt", score=0.7)
    provider = ScriptedProvider([ToolsUnsupportedError("no tools")])
    asked: list[str] = []

    def fallback(question: str) -> tuple[Iterator[str], list[SourceRef]]:
        asked.append(question)
        return iter(["From ", "your notes."]), [source]

    messages = user_turn("what's in my notes?")
    events = list(make_agent(provider, registry, fallback).run(messages))

    assert asked == ["what's in my notes?"]
    assert tokens_of(events) == "From your notes."
    assert events[-1] == ChatSources(sources=[source])
    assert messages[-1] == ChatMessage(role="assistant", content="From your notes.")


def test_run_reraises_missing_tool_support_after_the_first_turn(registry: ToolRegistry) -> None:
    provider = ScriptedProvider([[make_call("lookup")], ToolsUnsupportedError("no tools")])

    with pytest.raises(ToolsUnsupportedError):
        list(make_agent(provider, registry).run(user_turn()))


def test_run_reraises_missing_tool_support_when_resuming(registry: ToolRegistry) -> None:
    provider = ScriptedProvider([ToolsUnsupportedError("no tools")])
    messages = paused_history(make_call("launch"))

    with pytest.raises(ToolsUnsupportedError):
        list(make_agent(provider, registry).run(messages, ConfirmRequest(call_id="c1", approved=False)))


def test_run_reraises_missing_tool_support_once_text_has_streamed(registry: ToolRegistry) -> None:
    class HalfwayProvider(ScriptedProvider):
        def stream_chat(self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]) -> Iterator[Any]:
            yield TextDelta(text="Partial")
            raise ToolsUnsupportedError("no tools")

    with pytest.raises(ToolsUnsupportedError):
        list(make_agent(HalfwayProvider([]), registry).run(user_turn()))


def test_run_propagates_provider_errors(registry: ToolRegistry) -> None:
    provider = ScriptedProvider([ProviderError("model offline")])

    with pytest.raises(ProviderError, match="model offline"):
        list(make_agent(provider, registry).run(user_turn()))


def test_run_dedupes_sources_case_insensitively(registry: ToolRegistry) -> None:
    first = SourceRef(file_name="Report.pdf", file_path="C:/Docs/Report.pdf", score=0.9)
    same_file = first.model_copy(update={"file_path": "c:/docs/report.PDF", "score": 0.4})
    for name, source in (("twice", first), ("again", same_file)):
        registry.register(
            Tool(simple_spec(name), RecordingTool(ToolResult(content=name, sources=[source])), lambda a: "x")
        )
    provider = ScriptedProvider([[make_call("twice", "c1"), make_call("again", "c2")], [TextDelta(text="ok")]])

    events = list(make_agent(provider, registry).run(user_turn()))

    assert events[-1] == ChatSources(sources=[first])


def test_run_cuts_long_tool_results_short(registry: ToolRegistry) -> None:
    registry.register(Tool(simple_spec("dump"), RecordingTool(ToolResult(content="x" * 50000)), lambda a: "dump"))
    provider = ScriptedProvider([[make_call("dump")], [TextDelta(text="ok")]])
    messages = user_turn()

    list(make_agent(provider, registry).run(messages))

    assert len(messages[2].content) < MAX_TOOL_RESULT_CHARS + 50
    assert messages[2].content.endswith("[cut short]")


def test_run_trims_long_history_to_start_at_a_user_message(registry: ToolRegistry) -> None:
    history: list[ChatMessage] = []
    for i in range(CONTEXT_MESSAGES):
        history += [
            ChatMessage(role="user", content=f"q{i}"),
            ChatMessage(role="assistant", tool_calls=[make_call("lookup", f"c{i}")]),
            ChatMessage(role="tool", content="r", tool_call_id=f"c{i}", tool_name="lookup"),
        ]
    history.append(ChatMessage(role="user", content="latest"))
    provider = ScriptedProvider([[TextDelta(text="ok")]])

    list(make_agent(provider, registry).run(history))

    seen = provider.seen[0]
    assert seen[0].role == "user"
    assert len(seen) <= CONTEXT_MESSAGES


def test_run_keeps_the_latest_user_message_when_a_tool_run_fills_the_window(registry: ToolRegistry) -> None:
    history = [*user_turn("old"), ChatMessage(role="assistant", content="old answer"), *user_turn("dig deep")]
    for i in range(CONTEXT_MESSAGES):
        history += [
            ChatMessage(role="assistant", tool_calls=[make_call("lookup", f"c{i}")]),
            ChatMessage(role="tool", content="r", tool_call_id=f"c{i}", tool_name="lookup"),
        ]
    provider = ScriptedProvider([[TextDelta(text="ok")]])

    list(make_agent(provider, registry).run(history))

    assert provider.seen[0][0] == ChatMessage(role="user", content="dig deep")


def test_pending_tool_calls_returns_only_unanswered_calls() -> None:
    messages = [
        *paused_history(make_call("lookup", "c1"), make_call("launch", "c2")),
        ChatMessage(role="tool", content="r", tool_call_id="c1", tool_name="lookup"),
    ]

    assert [c.id for c in pending_tool_calls(messages)] == ["c2"]


def test_pending_tool_calls_is_empty_without_an_assistant_message() -> None:
    assert pending_tool_calls(user_turn()) == []


def test_run_saves_the_step_limit_note_in_the_history(registry: ToolRegistry) -> None:
    get_settings().max_agent_steps = 1
    provider = ScriptedProvider([[make_call("lookup", "c1")]])
    messages = user_turn()

    list(make_agent(provider, registry).run(messages))

    assert messages[-1] == ChatMessage(role="assistant", content=STEP_LIMIT_MESSAGE.strip())


def test_run_offers_no_tools_for_a_question_about_an_attachment(registry: ToolRegistry) -> None:
    provider = ScriptedProvider([[TextDelta(text="It says hello.")]])
    question = with_attachment("What does this say?", "Screenshot", "hello")

    list(make_agent(provider, registry).run([ChatMessage(role="user", content=question)]))

    assert provider.tools_seen == [[]]


def test_run_offers_tools_again_for_a_follow_up_without_one(registry: ToolRegistry) -> None:
    provider = ScriptedProvider([[TextDelta(text="Sure.")]])
    messages = [
        ChatMessage(role="user", content=with_attachment("What does this say?", "Screenshot", "hello")),
        ChatMessage(role="assistant", content="It says hello."),
        ChatMessage(role="user", content="Find my resume"),
    ]

    list(make_agent(provider, registry).run(messages))

    assert provider.tools_seen[0] != []


def test_run_says_so_when_the_model_returns_nothing(registry: ToolRegistry) -> None:
    provider = ScriptedProvider([[]])
    messages = user_turn()

    events = list(make_agent(provider, registry).run(messages))

    assert tokens_of(events) == EMPTY_ANSWER_MESSAGE
    assert messages[-1].content == EMPTY_ANSWER_MESSAGE


def test_source_tracker_prefers_files_that_were_read() -> None:
    tracker = SourceTracker()
    listed = SourceRef(file_name="setup.exe", file_path="C:/Downloads/setup.exe", score=1.0)
    read = SourceRef(file_name="pilot.pdf", file_path="C:/Downloads/pilot.pdf", score=1.0)

    tracker.add([listed], listing=True)
    tracker.add([read])

    assert tracker.final() == [read]


def test_source_tracker_falls_back_to_listed_files() -> None:
    tracker = SourceTracker()
    listed = SourceRef(file_name="setup.exe", file_path="C:/Downloads/setup.exe", score=1.0)

    tracker.add([listed], listing=True)

    assert tracker.final() == [listed]
