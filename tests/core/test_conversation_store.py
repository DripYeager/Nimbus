from __future__ import annotations

from collections.abc import Iterator
from itertools import count
from pathlib import Path

import pytest

from core.conversation_store import TITLE_MAX_CHARS, ConversationStore, make_title
from core.exceptions import ConversationNotFoundError, NimbusError
from models.chat import ChatMessage, ToolCall


@pytest.fixture
def store(tmp_path: Path) -> ConversationStore:
    store = ConversationStore(tmp_path / "chats" / "conversations.db")
    store.connect()
    return store


@pytest.fixture
def ticking_clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every time.time() call is one second later, so ordering by updated_at is deterministic."""
    ticks = count(1_700_000_000)
    monkeypatch.setattr("core.conversation_store.time.time", lambda: float(next(ticks)))
    yield


def test_connect_creates_the_database_folder(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "nested" / "conversations.db")

    store.connect()

    assert (tmp_path / "nested" / "conversations.db").exists()


def test_connect_raises_when_the_folder_cannot_be_created(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a folder", encoding="utf-8")

    with pytest.raises(NimbusError, match="Couldn't open chat history"):
        ConversationStore(blocker / "conversations.db").connect()


def test_create_titles_the_conversation_after_the_first_message(store: ConversationStore) -> None:
    conversation_id = store.create("find my   tax\nreturn")

    assert store.list_recent()[0].id == conversation_id
    assert store.list_recent()[0].title == "find my tax return"


def test_load_returns_an_empty_list_for_a_new_conversation(store: ConversationStore) -> None:
    assert store.load(store.create("hi")) == []


def test_append_round_trips_tool_calls_and_results(store: ConversationStore) -> None:
    conversation_id = store.create("open spotify")
    messages = [
        ChatMessage(role="user", content="open spotify"),
        ChatMessage(role="assistant", tool_calls=[ToolCall(id="c1", name="open_app", arguments={"name": "Spotify"})]),
        ChatMessage(role="tool", content="Opened Spotify.", tool_call_id="c1", tool_name="open_app"),
    ]

    store.append(conversation_id, messages)

    assert store.load(conversation_id) == messages


def test_append_raises_for_an_unknown_conversation(store: ConversationStore) -> None:
    with pytest.raises(ConversationNotFoundError):
        store.append("missing", [ChatMessage(role="user", content="hi")])


def test_load_raises_for_an_unknown_conversation(store: ConversationStore) -> None:
    with pytest.raises(ConversationNotFoundError):
        store.load("missing")


def test_list_recent_puts_the_latest_activity_first(store: ConversationStore, ticking_clock: None) -> None:
    older = store.create("first")
    newer = store.create("second")

    store.append(older, [ChatMessage(role="user", content="bump")])

    assert [c.id for c in store.list_recent()] == [older, newer]


def test_list_recent_respects_the_limit(store: ConversationStore, ticking_clock: None) -> None:
    for i in range(3):
        store.create(f"chat {i}")

    assert [c.title for c in store.list_recent(limit=2)] == ["chat 2", "chat 1"]


def test_delete_removes_the_conversation_and_its_messages(store: ConversationStore) -> None:
    conversation_id = store.create("bye")
    store.append(conversation_id, [ChatMessage(role="user", content="bye")])

    store.delete(conversation_id)

    with pytest.raises(ConversationNotFoundError):
        store.load(conversation_id)


def test_require_raises_with_an_actionable_message(store: ConversationStore) -> None:
    with pytest.raises(ConversationNotFoundError, match="may have been deleted"):
        store.require("missing")


def test_create_raises_before_connect(tmp_path: Path) -> None:
    with pytest.raises(NimbusError, match="call connect"):
        ConversationStore(tmp_path / "conversations.db").create("hi")


def test_make_title_keeps_a_short_message_whole() -> None:
    assert make_title("  open\tspotify  ") == "open spotify"


def test_make_title_shortens_a_long_message_with_an_ellipsis() -> None:
    title = make_title("word " * 40)

    assert len(title) <= TITLE_MAX_CHARS
    assert title.endswith("…")
    assert not title[:-1].endswith(" ")
