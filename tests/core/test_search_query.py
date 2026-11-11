from __future__ import annotations

import pytest

from core.search_query import (
    KEYWORD_WEIGHT_EXACT,
    KEYWORD_WEIGHT_NATURAL,
    MAX_TERMS,
    build_fts_query,
    keyword_weight,
)


def test_build_fts_query_drops_filler_words() -> None:
    assert build_fts_query("what does the contract say about termination?") == '"contract" OR "termination"'


def test_build_fts_query_keeps_a_code_as_one_quoted_phrase() -> None:
    assert build_fts_query("INV-2231") == '"INV-2231"'


def test_build_fts_query_strips_sentence_punctuation() -> None:
    assert build_fts_query("budget, forecast.") == '"budget" OR "forecast"'


def test_build_fts_query_neutralises_query_syntax() -> None:
    assert build_fts_query('budget AND (draft "notes') == '"budget" OR "draft" OR "notes"'


def test_build_fts_query_ignores_repeated_words_regardless_of_case() -> None:
    assert build_fts_query("Report report REPORT") == '"Report"'


def test_build_fts_query_returns_none_when_only_filler_is_left() -> None:
    assert build_fts_query("what is the") is None


def test_build_fts_query_caps_the_number_of_terms() -> None:
    words = " ".join(f"word{i}" for i in range(MAX_TERMS + 5))

    assert build_fts_query(words).count(" OR ") == MAX_TERMS - 1


@pytest.mark.parametrize(
    "text",
    ["INV-2231", "what does fault E119 mean", "VPN keeps dropping", '"termination fee"', "email from Priya"],
)
def test_keyword_weight_counts_keywords_for_exact_questions(text: str) -> None:
    assert keyword_weight(text) == KEYWORD_WEIGHT_EXACT


@pytest.mark.parametrize(
    "text", ["how much did we pay for the desks", "height-adjustable tables", "where did we eat noodles"]
)
def test_keyword_weight_leaves_natural_questions_to_meaning(text: str) -> None:
    assert keyword_weight(text) == KEYWORD_WEIGHT_NATURAL
