from __future__ import annotations

from core.search_query import MAX_TERMS, build_fts_query


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
