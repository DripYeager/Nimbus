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
# Each part is one model call, which a local model can take a minute over. A 200-page document
# would otherwise mean dozens of calls and a reply that seems to hang, so a very long document
# is summarized from this many evenly spaced parts (its start, its end and the middle between).
MAX_SUMMARY_PARTS = 4
SAMPLED_NOTE = "\n\n_Summary based on {used} evenly spaced sections of {total}. Ask about a part for detail._"
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
    (at most MAX_SUMMARY_PARTS of them) and then summarizes the summaries."""
    if not text.strip():
        return NOTHING_TO_SUMMARIZE_MESSAGE
    parts = chunk_text(text, chunk_size=SAFE_PROMPT_WORD_LIMIT, overlap=0)
    if len(parts) <= 1:
        return provider.complete(build_summarize_prompt(text))
    sampled = _evenly_spaced(parts, MAX_SUMMARY_PARTS)
    partial_summaries = [provider.complete(build_summarize_prompt(part)) for part in sampled]
    note = SAMPLED_NOTE.format(used=len(sampled), total=len(parts)) if len(sampled) < len(parts) else ""
    # Each summary is far shorter than its part, so recursing on the joined summaries always
    # converges, and keeps the final prompt inside the word budget for very long documents.
    return summarize_text("\n\n".join(partial_summaries), provider) + note


def _evenly_spaced(parts: list[str], limit: int) -> list[str]:
    """At most limit parts, always including the first and the last."""
    if len(parts) <= limit:
        return parts
    step = (len(parts) - 1) / (limit - 1)
    return [parts[round(index * step)] for index in range(limit)]
