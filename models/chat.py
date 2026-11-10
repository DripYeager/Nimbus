"""
Defines the provider-neutral chat, tool-calling and streamed-event shapes shared by the LLM
providers, the agent loop, the API and the chat window. Validation only; no behaviour.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from models.schema import IndexStatus, SourceRef

ProviderName = Literal["ollama", "openai", "anthropic", "openai_compatible"]


class ProviderConfig(BaseModel):
    """Everything needed to build one provider, from saved settings, or from unsaved values
    the user is trying out with "Test connection"."""

    name: ProviderName
    model: str
    api_key: str | None = None
    base_url: str | None = None


class ToolSpec(BaseModel):
    """A tool as the model sees it: a name, what it's for, and a JSON-schema for its arguments."""

    name: str
    description: str
    parameters: dict[str, Any]


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    """One turn of a conversation. Assistant turns may carry tool calls; tool turns carry the
    result of exactly one call, matched back to it by tool_call_id."""

    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    tool_name: str | None = None


class TextDelta(BaseModel):
    """One streamed slice of the model's visible answer."""

    text: str


class ToolResult(BaseModel):
    """What a tool hands back: text for the model, and any files worth showing as sources."""

    content: str
    sources: list[SourceRef] = Field(default_factory=list)
    is_error: bool = False
    # True when the files were only listed or matched by name, not read. They're shown as
    # sources only if nothing in the turn was actually read or searched.
    listing: bool = False


class ConversationSummary(BaseModel):
    id: str
    title: str
    updated_at: datetime


class Attachment(BaseModel):
    """Something the user handed Nimbus with a question: a file (by path, any folder, since the
    user picked it themselves) or a piece of text, such as what they copied."""

    name: str
    path: str | None = None
    text: str | None = None


class ChatRequest(BaseModel):
    text: str
    conversation_id: str | None = None
    attachment: Attachment | None = None


class ConfirmRequest(BaseModel):
    call_id: str
    approved: bool
    always_allow: bool = False


# --- Streamed events, one SSE frame each -------------------------------------------------


class ChatStarted(BaseModel):
    conversation_id: str
    index_status: IndexStatus
    is_cloud: bool


class ChatToken(BaseModel):
    text: str


class ToolActivity(BaseModel):
    """A tool step shown as a small chip in the chat ("Searched your files")."""

    call_id: str
    tool: str
    label: str
    status: Literal["running", "done", "failed", "denied"]


class ChatSources(BaseModel):
    sources: list[SourceRef]


class ConfirmationNeeded(BaseModel):
    """The agent wants to run an action tool and is paused until the user approves or denies it."""

    call_id: str
    tool: str
    description: str


class ChatDone(BaseModel):
    used_llm: bool
    elapsed_ms: int
    awaiting_confirmation: bool = False


class ChatFailed(BaseModel):
    message: str


ChatEvent = ChatStarted | ChatToken | ToolActivity | ChatSources | ConfirmationNeeded | ChatDone | ChatFailed
