"""
Routes a request to one of the six intents: keyword rules first, LLM fallback only when
none of them match. Owns the routing decision only — does not execute any tool itself.
"""

from __future__ import annotations

import re

from config.settings import get_settings
from llm.prompts import build_intent_classify_prompt
from llm.provider import LLMProvider, get_provider
from models.schema import Intent

FILE_SEARCH_KEYWORDS = ["find", "where", "locate", "which file"]
METADATA_KEYWORDS = ["when", "last modified", "how big", "created"]
# open/launch/start/run alone can't tell an app from a file ("open the invoice.pdf") — that
# needs the app catalog from system_tools.build_app_catalog (task 4.3), not yet built.
APP_LAUNCH_KEYWORDS = ["open", "launch", "start", "run"]
SUMMARIZE_KEYWORDS = ["summarize", "tl;dr", "key points", "brief me"]
GENERAL_QA_KEYWORDS = ["what", "how", "why"]

DOWNLOAD_STEM_PATTERN = re.compile(r"\bdownload\w*\b")


def classify_intent(text: str, provider: LLMProvider | None = None) -> Intent:
    """Routes text to an intent: keyword rules first, LLM only when none of them match."""
    lowered = text.lower()
    if _matches_any(lowered, FILE_SEARCH_KEYWORDS):
        return Intent.FILE_SEARCH
    if _matches_any(lowered, METADATA_KEYWORDS):
        return Intent.METADATA
    if _matches_any(lowered, APP_LAUNCH_KEYWORDS):
        return Intent.APP_LAUNCH
    if _is_downloads_today(lowered):
        return Intent.DOWNLOADS_TODAY
    if _matches_any(lowered, SUMMARIZE_KEYWORDS):
        return Intent.SUMMARIZE
    if _matches_any(lowered, GENERAL_QA_KEYWORDS):
        return Intent.GENERAL_QA
    return _classify_with_llm(text, provider)


def _matches_any(lowered_text: str, phrases: list[str]) -> bool:
    """True if any phrase appears in lowered_text as a whole word or phrase, not a bare substring."""
    return any(re.search(rf"\b{re.escape(phrase)}\b", lowered_text) for phrase in phrases)


def _is_downloads_today(lowered_text: str) -> bool:
    """Needs the downloads topic (any inflection) plus a same-day cue — not just one of them."""
    return bool(DOWNLOAD_STEM_PATTERN.search(lowered_text)) and _matches_any(lowered_text, ["today"])


def _classify_with_llm(text: str, provider: LLMProvider | None) -> Intent:
    """Asks the configured LLM to pick an intent when no keyword rule matched."""
    provider = provider or get_provider(get_settings())
    answer = provider.complete(build_intent_classify_prompt(text)).strip().lower()
    for intent in Intent:
        if intent.value == answer:
            return intent
    return Intent.GENERAL_QA
