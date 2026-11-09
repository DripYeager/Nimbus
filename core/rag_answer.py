"""
Answers a question straight from retrieved excerpts with one model call — the fallback for
models that can't call tools. Owns that single retrieve-then-answer step only.
"""

from __future__ import annotations

from collections.abc import Iterator

from core.retriever import Retriever
from llm.prompts import build_qa_prompt
from llm.provider import LLMProvider
from models.schema import SourceRef
from tools.file_tools import rank_unique_files

NOTHING_FOUND_MESSAGE = "I couldn't find anything relevant in your files."


class RagAnswerer:
    """Retrieves excerpts for a question and streams an answer grounded in them."""

    def __init__(self, retriever: Retriever, provider: LLMProvider) -> None:
        self._retriever = retriever
        self._provider = provider

    def answer(self, question: str) -> tuple[Iterator[str], list[SourceRef]]:
        """(answer tokens, the files they came from). No excerpts means no model call."""
        chunks = self._retriever.retrieve(question)
        if not chunks:
            return iter([NOTHING_FOUND_MESSAGE]), []
        return self._provider.stream(build_qa_prompt(question, chunks)), rank_unique_files(chunks)
