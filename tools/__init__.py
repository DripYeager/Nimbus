"""File search, summarization, app launch — one module per intent that needs real logic."""

from __future__ import annotations

from tools.file_tools import find_files, get_metadata, list_recent, rank_unique_files
from tools.summary_tools import summarize_document, summarize_todays_downloads

__all__ = [
    "find_files",
    "get_metadata",
    "list_recent",
    "rank_unique_files",
    "summarize_document",
    "summarize_todays_downloads",
]
