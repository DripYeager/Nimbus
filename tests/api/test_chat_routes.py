from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from fastapi.testclient import TestClient

from core.service_container import AppServices
from core.sse import parse_sse_events
from models.chat import (
    ChatDone,
    ChatEvent,
    ChatMessage,
    ChatRequest,
    ChatStarted,
    ChatToken,
    ConfirmRequest,
    ConversationSummary,
    ToolCall,
)
from models.schema import IndexStatus


def _events(body: str) -> list[tuple[str, dict[str, object]]]:
    return list(parse_sse_events(body.splitlines()))


def _reply() -> Iterator[ChatEvent]:
    yield ChatStarted(conversation_id="c1", index_status=IndexStatus(), is_cloud=False)
    yield ChatToken(text="Hello")
    yield ChatDone(used_llm=True, elapsed_ms=12)


def test_chat_streams_the_reply_as_sse(client: TestClient, services: AppServices) -> None:
    services.chat.send.return_value = _reply()

    response = client.post("/chat", json={"text": "hi"})

    assert response.headers["content-type"].startswith("text/event-stream")
    assert [name for name, _ in _events(response.text)] == ["started", "token", "done"]


def test_chat_passes_the_request_to_the_chat_service(client: TestClient, services: AppServices) -> None:
    services.chat.send.return_value = iter([])

    client.post("/chat", json={"text": "hi", "conversation_id": "c1"})

    services.chat.send.assert_called_once_with(ChatRequest(text="hi", conversation_id="c1"))


def test_chat_ends_a_crashed_stream_with_error_and_done(client: TestClient, services: AppServices) -> None:
    def crashing() -> Iterator[ChatEvent]:
        yield ChatToken(text="Hel")
        raise RuntimeError("bug")

    services.chat.send.return_value = crashing()

    response = client.post("/chat", json={"text": "hi"})

    assert [name for name, _ in _events(response.text)] == ["token", "error", "done"]


def test_chat_rejects_a_body_without_text(client: TestClient) -> None:
    assert client.post("/chat", json={}).status_code == 422


def test_confirm_forwards_the_decision(client: TestClient, services: AppServices) -> None:
    services.chat.confirm.return_value = _reply()

    response = client.post("/chat/c1/confirm", json={"call_id": "t1", "approved": True, "always_allow": True})

    services.chat.confirm.assert_called_once_with("c1", ConfirmRequest(call_id="t1", approved=True, always_allow=True))
    assert _events(response.text)[-1][0] == "done"


def test_confirm_rejects_a_body_without_a_decision(client: TestClient) -> None:
    assert client.post("/chat/c1/confirm", json={"call_id": "t1"}).status_code == 422


def test_list_conversations_returns_the_recent_chats(client: TestClient, services: AppServices) -> None:
    services.conversations.list_recent.return_value = [
        ConversationSummary(id="c1", title="Taxes", updated_at=datetime(2026, 11, 10, 9, 0))
    ]

    response = client.get("/conversations")

    assert response.json() == [{"id": "c1", "title": "Taxes", "updated_at": "2026-11-10T09:00:00"}]


def test_get_conversation_hides_tool_messages_and_empty_tool_call_turns(
    client: TestClient, services: AppServices
) -> None:
    services.conversations.load.return_value = [
        ChatMessage(role="user", content="open spotify"),
        ChatMessage(role="assistant", tool_calls=[ToolCall(id="t1", name="open_app")]),
        ChatMessage(role="tool", content="Opened Spotify.", tool_call_id="t1", tool_name="open_app"),
        ChatMessage(role="assistant", content="Done, Spotify is open."),
    ]

    response = client.get("/conversations/c1")

    assert [(m["role"], m["content"]) for m in response.json()] == [
        ("user", "open spotify"),
        ("assistant", "Done, Spotify is open."),
    ]


def test_delete_conversation_deletes_it(client: TestClient, services: AppServices) -> None:
    response = client.delete("/conversations/c1")

    services.conversations.delete.assert_called_once_with("c1")
    assert response.json() == {"deleted": True}
