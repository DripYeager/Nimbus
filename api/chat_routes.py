"""
HTTP routes for chatting: send a message, answer a confirmation card, and browse or delete
saved conversations. Routes only delegate, the chat service does the work.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from api.dependencies import get_services
from api.sse_stream import stream_sse
from core.service_container import AppServices
from models.chat import ChatMessage, ChatRequest, ConfirmRequest, ConversationSummary, ConversationView

router = APIRouter()

SSE_MEDIA_TYPE = "text/event-stream"


@router.post("/chat")
def chat(body: ChatRequest, services: AppServices = Depends(get_services)) -> StreamingResponse:
    """Streams the reply to a new message as SSE events."""
    return StreamingResponse(stream_sse(services.chat.send(body)), media_type=SSE_MEDIA_TYPE)


@router.post("/chat/{conversation_id}/confirm")
def confirm(
    conversation_id: str, body: ConfirmRequest, services: AppServices = Depends(get_services)
) -> StreamingResponse:
    """Approves or declines a pending action and streams the rest of the reply."""
    return StreamingResponse(stream_sse(services.chat.confirm(conversation_id, body)), media_type=SSE_MEDIA_TYPE)


@router.get("/conversations")
def list_conversations(services: AppServices = Depends(get_services)) -> list[ConversationSummary]:
    return services.conversations.list_recent()


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, services: AppServices = Depends(get_services)) -> list[ChatMessage]:
    """The visible messages of a chat, user turns and the assistant's written answers."""
    messages = services.conversations.load(conversation_id)
    return [m for m in messages if m.role == "user" or (m.role == "assistant" and m.content.strip())]


@router.get("/conversations/{conversation_id}/view")
def get_conversation_view(conversation_id: str, services: AppServices = Depends(get_services)) -> ConversationView:
    """A chat ready to show again: replies with their steps, and any card still waiting."""
    return services.chat.view(conversation_id)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, services: AppServices = Depends(get_services)) -> dict[str, bool]:
    services.conversations.require(conversation_id)
    services.conversations.delete(conversation_id)
    return {"deleted": True}
