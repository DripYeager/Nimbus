"""
Reads a document's text for the assistant, and condenses text that's too long to hand over
whole, map-reduce over word-budgeted parts. Owns reading-for-the-model and summarizing only;
does not parse files itself beyond what document_parser provides, or choose a provider.
"""

from __future__ import annotations

from pathlib import Path

from core.document_parser import extract_document_text
from core.text_chunker import chunk_text
from llm.prompts import build_summarize_prompt
from llm.provider import LLMProvider

# A safe word budget per prompt, big enough to avoid pointless map-reduce on a typical
# document, small enough to fit comfortably in even a locally-hosted model's context window.
SAFE_PROMPT_WORD_LIMIT = 4000
NOTHING_TO_SUMMARIZE_MESSAGE = "Nothing to summarize: no text could be extracted."


def read_document_excerpt(path: Path, max_words: int) -> tuple[str, bool]:
    """Returns the first max_words words of a document's text, and whether it was cut short."""
    words = extract_document_text(path).split()
    return " ".join(words[:max_words]), len(words) > max_words


def summarize_document(path: Path, provider: LLMProvider) -> str:
    """Summarizes a whole document, however long it is."""
    return summarize_text(extract_document_text(path), provider)


def summarize_text(text: str, provider: LLMProvider) -> str:
    """Summarizes text in one call if it fits the word budget, otherwise summarizes each part
    and then summarizes the summaries."""
    if not text.strip():
        return NOTHING_TO_SUMMARIZE_MESSAGE
    parts = chunk_text(text, chunk_size=SAFE_PROMPT_WORD_LIMIT, overlap=0)
    if len(parts) <= 1:
        return provider.complete(build_summarize_prompt(text))
    partial_summaries = [provider.complete(build_summarize_prompt(part)) for part in parts]
    # Each summary is far shorter than its part, so recursing on the joined summaries always
    # converges, and keeps the final prompt inside the word budget for very long documents.
    return summarize_text("\n\n".join(partial_summaries), provider)
