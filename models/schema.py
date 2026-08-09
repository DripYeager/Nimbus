"""
Defines every data contract that crosses a module boundary in Nimbus, as Pydantic models.
Does not contain business logic — validation only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel


@dataclass
class ParsedDocument:
    """What document_parser hands to the indexer, before chunking or embedding happens."""

    markdown_text: str
    needs_ocr: bool


@dataclass
class FileMetadata:
    """A file's size and timestamps, read straight from the filesystem — no index lookup involved."""

    file_path: str
    file_name: str
    size_bytes: int
    created_at: datetime
    modified_at: datetime


class Intent(Enum):
    """What the user is actually asking for, as decided by intent_router."""

    FILE_SEARCH = "file_search"
    SUMMARIZE = "summarize"
    DOWNLOADS_TODAY = "downloads_today"
    APP_LAUNCH = "app_launch"
    METADATA = "metadata"
    GENERAL_QA = "general_qa"


class SourceRef(BaseModel):
    file_name: str
    file_path: str
    score: float


class AppEntry(BaseModel):
    name: str
    exe_path: str
    source: Literal["start_menu", "registry", "scan"]


class IndexStatus(BaseModel):
    total_files: int
    indexed_files: int
    pending: int
    is_paused: bool
    last_error: str | None = None


class IndexedChunk(BaseModel):
    """One row in LanceDB: an embedded chunk plus enough metadata to trace it back to its file."""

    id: str
    file_path: str
    file_name: str
    file_type: str
    content_hash: str
    chunk_index: int
    chunk_text: str
    vector: list[float]
    created_at: datetime
    modified_at: datetime
    indexed_at: datetime


class SearchResult(BaseModel):
    chunk_text: str
    file_path: str
    file_name: str
    score: float
    metadata: dict[str, Any]


class QueryRequest(BaseModel):
    text: str
    max_results: int = 5
    stream: bool = True


class QueryResponse(BaseModel):
    answer: str
    intent: Intent
    sources: list[SourceRef]
    used_llm: bool
    elapsed_ms: int


class QueryStarted(BaseModel):
    """Sent once routing resolves the intent and sources, before any answer tokens arrive."""

    intent: Intent
    sources: list[SourceRef]


class QueryToken(BaseModel):
    """One incremental slice of a streamed answer."""

    text: str


class QueryDone(BaseModel):
    """Terminal event closing out a streamed query, once every token has been sent."""

    used_llm: bool
    elapsed_ms: int


class QueryFailed(BaseModel):
    """Sent instead of QueryDone if a tool or provider failed partway through the stream."""

    message: str
