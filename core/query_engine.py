"""
Ties the query pipeline together: classify the intent, route to the matching tool, and
build a sourced, cost-tracked answer. Owns the routing sequence only — it composes existing
tools rather than implementing file search, metadata, or summarization logic itself.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from core.exceptions import QueryError
from core.intent_router import classify_intent
from core.retriever import Retriever
from core.vector_store import VectorStore
from llm.prompts import build_qa_prompt
from models.schema import Intent, QueryResponse, SourceRef

if TYPE_CHECKING:
    # Deferred, same reason as intent_router.py: llm.provider pulls in every concrete provider
    # module, one of which may import core.exceptions and re-enter this package mid-load.
    from llm.provider import LLMProvider

APP_LAUNCH_NOT_AVAILABLE_MESSAGE = "Launching apps isn't available yet."


class QueryEngine:
    """Routes one request to its intent's tool and returns a sourced, cost-tracked answer."""

    def __init__(self, retriever: Retriever, provider: LLMProvider, store: VectorStore) -> None:
        self._retriever = retriever
        self._provider = provider
        self._store = store

    def handle_query(self, text: str) -> QueryResponse:
        """Classifies text, routes it to the matching tool, and times the whole request."""
        start = time.monotonic()
        intent = classify_intent(text, provider=self._provider)
        tool_provider = _UsageTrackingProvider(self._provider)
        result = self._route(text, intent, tool_provider)
        return self._build_response(intent, result, tool_provider, start)

    def handle_downloads_today(self) -> QueryResponse:
        """Summarizes today's downloads directly — the intent is fixed by this entry point, so
        there's no free-text query to classify."""
        start = time.monotonic()
        tool_provider = _UsageTrackingProvider(self._provider)
        result = self._handle_downloads_today(tool_provider)
        return self._build_response(Intent.DOWNLOADS_TODAY, result, tool_provider, start)

    def _build_response(
        self,
        intent: Intent,
        result: tuple[str, list[SourceRef]],
        tool_provider: _UsageTrackingProvider,
        start: float,
    ) -> QueryResponse:
        """Shared response assembly for both handle_query and handle_downloads_today."""
        answer, sources = result
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return QueryResponse(
            answer=answer, intent=intent, sources=sources, used_llm=tool_provider.was_used, elapsed_ms=elapsed_ms
        )

    def _route(self, text: str, intent: Intent, provider: LLMProvider) -> tuple[str, list[SourceRef]]:
        """Dispatches to the handler for one intent — Intent is a closed enum, every value is listed."""
        if intent == Intent.FILE_SEARCH:
            return self._handle_file_search(text)
        if intent == Intent.METADATA:
            return self._handle_metadata(text)
        if intent == Intent.APP_LAUNCH:
            return APP_LAUNCH_NOT_AVAILABLE_MESSAGE, []
        if intent == Intent.DOWNLOADS_TODAY:
            return self._handle_downloads_today(provider)
        if intent == Intent.SUMMARIZE:
            return self._handle_summarize(text, provider)
        if intent == Intent.GENERAL_QA:
            return self._handle_general_qa(text, provider)
        raise QueryError(f"Unhandled intent: {intent}")

    def _handle_file_search(self, text: str) -> tuple[str, list[SourceRef]]:
        """Pure lookup — semantic search over indexed files, no LLM involved."""
        from tools.file_tools import find_files

        sources = find_files(self._retriever, text)
        if not sources:
            return self._nothing_found_message(), []
        names = ", ".join(source.file_name for source in sources)
        return f"Found {len(sources)} matching file(s): {names}", sources

    def _handle_metadata(self, text: str) -> tuple[str, list[SourceRef]]:
        """Pure lookup — resolves the target file by semantic search, then reads its stat() directly."""
        from tools.file_tools import find_files, get_metadata

        matches = find_files(self._retriever, text, top_k=1)
        if not matches:
            return self._nothing_found_message(), []
        metadata = get_metadata(Path(matches[0].file_path))
        if metadata is None:
            return f"{matches[0].file_name} no longer exists.", matches
        answer = (
            f"{metadata.file_name} — modified {metadata.modified_at:%Y-%m-%d %H:%M}, "
            f"created {metadata.created_at:%Y-%m-%d %H:%M}, {metadata.size_bytes:,} bytes"
        )
        return answer, matches

    def _handle_downloads_today(self, provider: LLMProvider) -> tuple[str, list[SourceRef]]:
        """Delegates to summary_tools — it decides for itself whether there's anything to summarize."""
        from tools.summary_tools import summarize_todays_downloads

        return summarize_todays_downloads(provider), []

    def _handle_summarize(self, text: str, provider: LLMProvider) -> tuple[str, list[SourceRef]]:
        """Resolves the target file by semantic search (no LLM), then summarizes it (LLM)."""
        from tools.file_tools import find_files
        from tools.summary_tools import summarize_document

        matches = find_files(self._retriever, text, top_k=1)
        if not matches:
            return self._nothing_found_message(), []
        return summarize_document(Path(matches[0].file_path), provider), matches

    def _handle_general_qa(self, text: str, provider: LLMProvider) -> tuple[str, list[SourceRef]]:
        """Retrieves chunks (no LLM), then synthesizes an answer from them (LLM) — skipped if nothing was found."""
        from tools.file_tools import rank_unique_files

        chunks = self._retriever.retrieve(text)
        if not chunks:
            return self._nothing_found_message(), []
        answer = provider.complete(build_qa_prompt(text, chunks))
        return answer, rank_unique_files(chunks)

    def _nothing_found_message(self) -> str:
        """A more honest message when the index itself is empty, rather than a generic 'not found'."""
        if self._store.count() == 0:
            return "Nothing has been indexed yet, so there's nothing to search."
        return "I couldn't find anything relevant to that."


class _UsageTrackingProvider:
    """Wraps an LLMProvider and records whether complete()/stream() was actually called — this is
    how used_llm gets set correctly regardless of which internal path a tool happens to take."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
        self.was_used = False

    def complete(self, prompt: str) -> str:
        self.was_used = True
        return self._provider.complete(prompt)

    def stream(self, prompt: str) -> Iterator[str]:
        self.was_used = True
        return self._provider.stream(prompt)

    def is_available(self) -> bool:
        return self._provider.is_available()
