from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from config.settings import get_settings
from core.chat_service import SKIPPED_MESSAGE, ChatService
from core.conversation_store import ConversationStore
from core.exceptions import ConversationNotFoundError, ProviderError
from core.fast_path import FastAnswer, FastPath
from models.chat import (
    Attachment,
    ChatDone,
    ChatEvent,
    ChatFailed,
    ChatMessage,
    ChatRequest,
    ChatSources,
    ChatStarted,
    ChatToken,
    ConfirmationNeeded,
    ConfirmRequest,
    ToolCall,
)
from models.schema import IndexStatus, SourceRef


class FakeAgent:
    """Appends one assistant reply, optionally asks for confirmation or fails, and records each run."""

    # Tools that must ask every time, so "always allow" is refused for them.
    always_ask = frozenset({"run_command"})

    def can_always_allow(self, tool_name: str) -> bool:
        return tool_name not in self.always_ask

    def __init__(self) -> None:
        self.reply = "Here you go."
        self.error: Exception | None = None
        self.ask_confirmation = False
        self.runs: list[tuple[list[ChatMessage], ConfirmRequest | None]] = []

    def run(self, messages: list[ChatMessage], decision: ConfirmRequest | None = None) -> Iterator[ChatEvent]:
        self.runs.append((list(messages), decision))
        messages.append(ChatMessage(role="assistant", content=self.reply))
        yield ChatToken(text=self.reply)
        if self.error is not None:
            raise self.error
        if self.ask_confirmation:
            yield ConfirmationNeeded(call_id="c9", tool="open_app", description="Open the app")


@pytest.fixture
def store(tmp_path: Path) -> ConversationStore:
    store = ConversationStore(tmp_path / "conversations.db")
    store.connect()
    return store


@pytest.fixture
def agent() -> FakeAgent:
    return FakeAgent()


@pytest.fixture
def fast_path(mocker: MockerFixture) -> FastPath:
    fast_path = mocker.Mock(spec=FastPath)
    fast_path.try_answer.return_value = None
    return fast_path


@pytest.fixture
def service(store: ConversationStore, agent: FakeAgent, fast_path: FastPath) -> ChatService:
    return ChatService(store, agent, fast_path, lambda: IndexStatus(indexed_files=3))


@pytest.fixture
def paused_chat(store: ConversationStore) -> str:
    """A conversation whose last assistant turn is waiting on an open_app confirmation."""
    conversation_id = store.create("open spotify please")
    store.append(
        conversation_id,
        [
            ChatMessage(role="user", content="open spotify please"),
            ChatMessage(role="assistant", tool_calls=[ToolCall(id="c1", name="open_app", arguments={"name": "x"})]),
        ],
    )
    return conversation_id


def test_send_creates_a_conversation_and_starts_with_its_id(service: ChatService, store: ConversationStore) -> None:
    events = list(service.send(ChatRequest(text="hello")))

    started = events[0]
    assert isinstance(started, ChatStarted)
    assert [c.id for c in store.list_recent()] == [started.conversation_id]
    assert started.index_status.indexed_files == 3


def test_send_raises_for_an_unknown_conversation(service: ChatService) -> None:
    with pytest.raises(ConversationNotFoundError):
        list(service.send(ChatRequest(text="hello", conversation_id="missing")))


def test_send_answers_from_the_fast_path_without_the_agent(
    service: ChatService, agent: FakeAgent, fast_path: FastPath
) -> None:
    source = SourceRef(file_name="report.pdf", file_path="C:/report.pdf", score=95)
    fast_path.try_answer.return_value = FastAnswer(text="Opening **report.pdf**.", sources=[source])

    events = list(service.send(ChatRequest(text="open report.pdf")))

    assert events[1:] == [
        ChatToken(text="Opening **report.pdf**."),
        ChatSources(sources=[source]),
        ChatDone(used_llm=False, elapsed_ms=events[-1].elapsed_ms),
    ]
    assert agent.runs == []


def test_send_saves_a_fast_path_exchange(service: ChatService, store: ConversationStore, fast_path: FastPath) -> None:
    fast_path.try_answer.return_value = FastAnswer(text="Opening **Spotify**.")

    events = list(service.send(ChatRequest(text="open spotify")))

    saved = store.load(events[0].conversation_id)
    assert [(m.role, m.content) for m in saved] == [("user", "open spotify"), ("assistant", "Opening **Spotify**.")]


def test_send_runs_the_agent_and_marks_the_reply_as_model_made(service: ChatService, agent: FakeAgent) -> None:
    events = list(service.send(ChatRequest(text="what's in my notes?")))

    assert events[-1].used_llm is True
    assert agent.runs[0][0][-1] == ChatMessage(role="user", content="what's in my notes?")


def test_send_saves_the_user_message_and_agent_reply(service: ChatService, store: ConversationStore) -> None:
    events = list(service.send(ChatRequest(text="summarize my week")))

    saved = store.load(events[0].conversation_id)
    assert [(m.role, m.content) for m in saved] == [("user", "summarize my week"), ("assistant", "Here you go.")]


def test_send_includes_earlier_history_for_the_agent(
    service: ChatService, store: ConversationStore, agent: FakeAgent
) -> None:
    first = list(service.send(ChatRequest(text="first question")))
    conversation_id = first[0].conversation_id

    list(service.send(ChatRequest(text="follow-up", conversation_id=conversation_id)))

    assert [m.content for m in agent.runs[1][0]] == ["first question", "Here you go.", "follow-up"]


def test_send_reports_a_nimbus_error_as_chat_failed(service: ChatService, agent: FakeAgent) -> None:
    agent.error = ProviderError("The model is offline.")

    events = list(service.send(ChatRequest(text="hi")))

    assert ChatFailed(message="The model is offline.") in events
    assert isinstance(events[-1], ChatDone)


def test_send_saves_agent_messages_even_when_the_agent_fails(
    service: ChatService, store: ConversationStore, agent: FakeAgent
) -> None:
    agent.error = ProviderError("The model is offline.")

    events = list(service.send(ChatRequest(text="hi")))

    assert [m.role for m in store.load(events[0].conversation_id)] == ["user", "assistant"]


def test_send_saves_agent_messages_when_an_unexpected_error_escapes(
    service: ChatService, store: ConversationStore, agent: FakeAgent
) -> None:
    agent.error = RuntimeError("bug")
    events: list[ChatEvent] = []

    with pytest.raises(RuntimeError):
        for event in service.send(ChatRequest(text="hi")):
            events.append(event)

    assert [m.role for m in store.load(events[0].conversation_id)] == ["user", "assistant"]


def test_send_flags_done_as_awaiting_confirmation(service: ChatService, agent: FakeAgent) -> None:
    agent.ask_confirmation = True

    events = list(service.send(ChatRequest(text="open spotify and play jazz")))

    assert events[-1].awaiting_confirmation is True


def test_send_skips_an_unanswered_action_when_a_new_message_arrives(
    service: ChatService, store: ConversationStore, agent: FakeAgent, paused_chat: str
) -> None:
    list(service.send(ChatRequest(text="never mind, what time is it?", conversation_id=paused_chat)))

    saved = store.load(paused_chat)
    assert saved[2] == ChatMessage(role="tool", content=SKIPPED_MESSAGE, tool_call_id="c1", tool_name="open_app")
    assert saved[3] == ChatMessage(role="user", content="never mind, what time is it?")


def test_send_gives_the_agent_a_history_with_nothing_left_pending(
    service: ChatService, agent: FakeAgent, paused_chat: str
) -> None:
    list(service.send(ChatRequest(text="never mind", conversation_id=paused_chat)))

    history, decision = agent.runs[0]
    assert decision is None
    assert [m.role for m in history] == ["user", "assistant", "tool", "user"]


def test_confirm_rejects_a_call_that_is_not_pending(service: ChatService, agent: FakeAgent, paused_chat: str) -> None:
    events = list(service.confirm(paused_chat, ConfirmRequest(call_id="stale", approved=True)))

    assert events == [ChatFailed(message="That action is no longer waiting for an answer.")]
    assert agent.runs == []


def test_confirm_resumes_the_agent_with_the_decision(service: ChatService, agent: FakeAgent, paused_chat: str) -> None:
    decision = ConfirmRequest(call_id="c1", approved=True)

    events = list(service.confirm(paused_chat, decision))

    assert isinstance(events[0], ChatStarted)
    assert agent.runs[0][1] == decision


def test_confirm_saves_only_the_new_messages(service: ChatService, store: ConversationStore, paused_chat: str) -> None:
    list(service.confirm(paused_chat, ConfirmRequest(call_id="c1", approved=False)))

    assert [m.role for m in store.load(paused_chat)] == ["user", "assistant", "assistant"]


def test_confirm_with_always_allow_saves_the_tool(
    service: ChatService, paused_chat: str, mocker: MockerFixture
) -> None:
    save = mocker.patch("core.chat_service.save_user_settings")

    list(service.confirm(paused_chat, ConfirmRequest(call_id="c1", approved=True, always_allow=True)))

    save.assert_called_once_with({"auto_approved_tools": ["open_app"]})


def test_confirm_with_always_allow_skips_saving_an_already_allowed_tool(
    service: ChatService, paused_chat: str, mocker: MockerFixture
) -> None:
    get_settings().auto_approved_tools = ["open_app"]
    save = mocker.patch("core.chat_service.save_user_settings")

    list(service.confirm(paused_chat, ConfirmRequest(call_id="c1", approved=True, always_allow=True)))

    save.assert_not_called()


def test_confirm_ignores_always_allow_on_a_decline(
    service: ChatService, paused_chat: str, mocker: MockerFixture
) -> None:
    save = mocker.patch("core.chat_service.save_user_settings")

    list(service.confirm(paused_chat, ConfirmRequest(call_id="c1", approved=False, always_allow=True)))

    save.assert_not_called()


def test_confirm_raises_for_an_unknown_conversation(service: ChatService) -> None:
    with pytest.raises(ConversationNotFoundError):
        list(service.confirm("missing", ConfirmRequest(call_id="c1", approved=True)))


def test_send_gives_the_agent_the_attached_text_and_skips_the_fast_path(
    service: ChatService, agent: FakeAgent, fast_path: FastPath
) -> None:
    request = ChatRequest(text="Translate this", attachment=Attachment(name="Copied text", text="Bonjour"))

    list(service.send(request))

    [(messages, _)] = agent.runs
    assert "Bonjour" in messages[-1].content
    fast_path.try_answer.assert_not_called()


def test_confirm_with_always_allow_on_a_file_allows_every_file_type(
    service: ChatService, store: ConversationStore, mocker: MockerFixture
) -> None:
    conversation_id = store.create("make a sheet")
    call = ToolCall(id="c2", name="create_spreadsheet", arguments={"file_name": "a.xlsx", "csv": "a"})
    store.append(
        conversation_id, [ChatMessage(role="user", content="x"), ChatMessage(role="assistant", tool_calls=[call])]
    )
    save = mocker.patch("core.chat_service.save_user_settings")

    list(service.confirm(conversation_id, ConfirmRequest(call_id="c2", approved=True, always_allow=True)))

    save.assert_called_once_with({"auto_approved_tools": ["create_document", "create_spreadsheet"]})


def test_confirm_never_saves_always_allow_for_a_tool_that_must_ask(
    service: ChatService, store: ConversationStore, mocker: MockerFixture
) -> None:
    conversation_id = store.create("run something")
    call = ToolCall(id="c3", name="run_command", arguments={"command": "Remove-Item x"})
    messages = [ChatMessage(role="user", content="x"), ChatMessage(role="assistant", tool_calls=[call])]
    store.append(conversation_id, messages)
    save = mocker.patch("core.chat_service.save_user_settings")

    list(service.confirm(conversation_id, ConfirmRequest(call_id="c3", approved=True, always_allow=True)))

    save.assert_not_called()
