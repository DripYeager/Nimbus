from __future__ import annotations

import pytest

from core.text_chunker import chunk_text


def test_chunk_text_returns_correct_overlap() -> None:
    text = "a b c d e f g h i j"
    assert chunk_text(text, chunk_size=4, overlap=1) == ["a b c d", "d e f g", "g h i j"]


def test_chunk_text_returns_a_single_chunk_when_text_is_shorter_than_chunk_size() -> None:
    assert chunk_text("one two three", chunk_size=512, overlap=50) == ["one two three"]


def test_chunk_text_returns_empty_list_for_empty_input() -> None:
    assert chunk_text("", chunk_size=4, overlap=1) == []


def test_chunk_text_treats_whitespace_only_input_as_empty() -> None:
    assert chunk_text("   \n\t  ", chunk_size=4, overlap=1) == []


def test_chunk_text_raises_when_chunk_size_is_not_positive() -> None:
    with pytest.raises(ValueError):
        chunk_text("a b c", chunk_size=0, overlap=0)


def test_chunk_text_raises_when_overlap_is_negative() -> None:
    with pytest.raises(ValueError):
        chunk_text("a b c", chunk_size=4, overlap=-1)


def test_chunk_text_raises_when_overlap_is_not_smaller_than_chunk_size() -> None:
    with pytest.raises(ValueError):
        chunk_text("a b c", chunk_size=4, overlap=4)
