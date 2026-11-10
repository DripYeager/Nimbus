"""
Defines the indexing, search and app-catalog data contracts that cross module boundaries.
Does not contain business logic — validation only. Chat and agent shapes live in chat.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, field_validator


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


@dataclass(frozen=True)
class ScannedFile:
    """One file seen on disk during a source scan — just enough to tell if it changed."""

    path: Path
    size_bytes: int
    modified_ts: float


class FileCategory(StrEnum):
    """The file-type groups a user can switch content indexing on or off for."""

    DOCUMENTS = "documents"
    PDFS = "pdfs"
    SPREADSHEETS = "spreadsheets"
    SLIDES = "slides"
    TEXT = "text"
    CODE = "code"
    EMAIL = "email"


class IndexSource(BaseModel):
    """A folder the user chose to index. include_contents=False keeps it searchable by file
    name only, which is instant and never reads a file's bytes."""

    path: Path
    include_contents: bool = True

    @field_validator("path", mode="before")
    @classmethod
    def _expand_home(cls, value: str | Path) -> Path:
        """Lets saved settings and .env use ~."""
        return Path(value).expanduser()


class CatalogStatus(StrEnum):
    """Where one cataloged file is in the content-indexing pipeline."""

    PENDING = "pending"
    INDEXED = "indexed"
    NAME_ONLY = "name_only"
    FAILED = "failed"


@dataclass(frozen=True)
class CatalogEntry:
    """One file's row in the catalog: what it looked like when last seen, and its index status."""

    path: Path
    size_bytes: int
    modified_ts: float
    status: CatalogStatus


@dataclass
class SyncPlan:
    """What a source scan decided: catalog rows to write, files to queue for content
    indexing, and files whose content rows must go because they're now name-only."""

    upserts: list[CatalogEntry] = field(default_factory=list)
    to_queue: list[tuple[Path, float]] = field(default_factory=list)
    drop_content: list[Path] = field(default_factory=list)


class SourceRef(BaseModel):
    file_name: str
    file_path: str
    score: float


class AppEntry(BaseModel):
    """One launchable app. launch_target is a shortcut path, an exe path, or a Store app ID."""

    name: str
    launch_target: str
    source: Literal["start_menu", "registry", "store_app"]


class IndexStatus(BaseModel):
    """A snapshot of indexing progress, shown in the tray, the chat header and Settings."""

    cataloged_files: int = 0
    content_files: int = 0
    indexed_files: int = 0
    pending_files: int = 0
    failed_files: int = 0
    is_paused: bool = False
    is_scanning: bool = False
    current_file: str | None = None
    current_path: str | None = None

    @property
    def is_busy(self) -> bool:
        """True while there's still scanning or content indexing left to do."""
        return self.is_scanning or self.pending_files > 0

    @property
    def progress_ratio(self) -> float:
        """Fraction of content-indexable files already done, 1.0 when there's nothing to do."""
        if self.content_files == 0:
            return 1.0
        return min(1.0, (self.indexed_files + self.failed_files) / self.content_files)


class SourceSummary(BaseModel):
    """Per-folder counts for the Settings window's Sources list."""

    path: str
    include_contents: bool
    exists: bool
    file_count: int
    indexed_count: int
    pending_count: int = 0
    failed_count: int = 0
    # True while the file being indexed right now lives in this folder.
    is_active: bool = False
    current_file: str | None = None

    @property
    def content_count(self) -> int:
        """Files in this folder whose contents are being read (done, waiting or failed)."""
        return self.indexed_count + self.pending_count + self.failed_count

    @property
    def progress_ratio(self) -> float:
        """Share of this folder's content files already handled; 1.0 when there's nothing to do."""
        if self.content_count == 0:
            return 1.0
        return (self.indexed_count + self.failed_count) / self.content_count


class IndexedChunk(BaseModel):
    """One indexed chunk: its text, embedding, and enough metadata to trace it back to its file."""

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
    chunk_id: str
    chunk_text: str
    file_path: str
    file_name: str
    score: float
    metadata: dict[str, Any]


class CatalogMatch(BaseModel):
    """A file found by name in the catalog, with a 0-100 fuzzy match score."""

    file_path: str
    file_name: str
    size_bytes: int
    modified_at: datetime
    score: float
