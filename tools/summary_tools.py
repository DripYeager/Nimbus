"""
Summarizes one document or today's downloads — the only two tools that call the LLM.
Owns prompt orchestration and map-reduce for large text. Does not parse files itself
beyond what document_parser already provides, and does not choose which provider to use.
"""

from __future__ import annotations

from datetime import datetime, time
from pathlib import Path

from config.settings import get_settings
from core.document_parser import extract_document_text
from core.text_chunker import chunk_text
from llm.prompts import build_summarize_prompt
from llm.provider import LLMProvider
from models.schema import FileMetadata
from tools.file_tools import list_recent

# A safe word budget per prompt — big enough to avoid pointless map-reduce on a typical
# document, small enough to fit comfortably in even a locally-hosted model's context window.
SAFE_PROMPT_WORD_LIMIT = 4000
NOTHING_TO_SUMMARIZE_MESSAGE = "Nothing to summarize — no text could be extracted."


def summarize_document(path: Path, provider: LLMProvider) -> str:
    """Summarizes one file, map-reducing it in parts first if its text is too large for one prompt."""
    return _summarize_text(extract_document_text(path), provider)


def summarize_todays_downloads(provider: LLMProvider) -> str:
    """Summarizes everything modified in the Downloads folder since midnight today, in one batch."""
    downloads_dir = _find_downloads_dir()
    if downloads_dir is None:
        return "Downloads isn't one of the watched folders, so there's nothing to summarize."

    since_midnight = datetime.combine(datetime.now().date(), time.min)
    files = list_recent(downloads_dir, modified_after=since_midnight)
    if not files:
        return "No files were downloaded today."

    return _summarize_text(_combine_files_for_summary(files), provider)


def _summarize_text(text: str, provider: LLMProvider) -> str:
    """Summarizes text in one call if it's small enough, otherwise map-reduces it in parts."""
    if not text.strip():
        return NOTHING_TO_SUMMARIZE_MESSAGE
    parts = chunk_text(text, chunk_size=SAFE_PROMPT_WORD_LIMIT, overlap=0)
    if len(parts) <= 1:
        return provider.complete(build_summarize_prompt(text))
    partial_summaries = [provider.complete(build_summarize_prompt(part)) for part in parts]
    return provider.complete(build_summarize_prompt("\n\n".join(partial_summaries)))


def _find_downloads_dir() -> Path | None:
    """Finds the configured watched directory literally named Downloads, if any."""
    for directory in get_settings().watched_dirs:
        if directory.name.lower() == "downloads":
            return directory
    return None


def _combine_files_for_summary(files: list[FileMetadata]) -> str:
    """Joins each file's extracted text under its own filename header for one combined call."""
    sections = []
    for file in files:
        text = extract_document_text(Path(file.file_path))
        if text.strip():
            sections.append(f"## {file.file_name}\n{text}")
    return "\n\n".join(sections)
