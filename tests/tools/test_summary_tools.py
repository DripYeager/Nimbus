from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from core.exceptions import ParsingError, ProviderError
from llm.provider import LLMProvider
from tools.summary_tools import (
    MAX_SUMMARY_PARTS,
    NOTHING_TO_SUMMARIZE_MESSAGE,
    SAFE_PROMPT_WORD_LIMIT,
    _evenly_spaced,
    read_document_excerpt,
    summarize_document,
    summarize_text,
)


@pytest.fixture
def provider(mocker: MockerFixture) -> Mock:
    provider = mocker.Mock(spec=LLMProvider)
    provider.complete.return_value = "five bullet points"
    return provider


def test_summarize_text_uses_one_call_for_a_short_text(provider: Mock) -> None:
    summary = summarize_text("A short document about invoices.", provider)

    assert summary == "five bullet points"
    provider.complete.assert_called_once()
    assert "A short document about invoices." in provider.complete.call_args.args[0]


def test_summarize_text_map_reduces_a_long_text(provider: Mock) -> None:
    provider.complete.side_effect = ["part one", "part two", "part three", "final summary"]

    summary = summarize_text("word " * (SAFE_PROMPT_WORD_LIMIT * 2 + 1000), provider)

    assert summary == "final summary"
    final_prompt = provider.complete.call_args.args[0]
    assert "part one" in final_prompt
    assert "part three" in final_prompt


def test_summarize_text_skips_the_model_for_blank_text(provider: Mock) -> None:
    assert summarize_text("  \n ", provider) == NOTHING_TO_SUMMARIZE_MESSAGE
    provider.complete.assert_not_called()


def test_summarize_text_propagates_provider_errors(provider: Mock) -> None:
    provider.complete.side_effect = ProviderError("offline")

    with pytest.raises(ProviderError):
        summarize_text("some text", provider)


def test_summarize_document_summarizes_the_extracted_text(provider: Mock, mocker: MockerFixture) -> None:
    mocker.patch("tools.summary_tools.extract_document_text", return_value="Board minutes from March.")

    assert summarize_document(Path("minutes.docx"), provider) == "five bullet points"
    assert "Board minutes from March." in provider.complete.call_args.args[0]


def test_summarize_document_propagates_parsing_errors(provider: Mock, mocker: MockerFixture) -> None:
    mocker.patch("tools.summary_tools.extract_document_text", side_effect=ParsingError("corrupt file"))

    with pytest.raises(ParsingError):
        summarize_document(Path("broken.docx"), provider)


def test_read_document_excerpt_cuts_to_the_word_budget(tmp_path: Path) -> None:
    path = tmp_path / "long.txt"
    path.write_text("one two three four five", encoding="utf-8")

    assert read_document_excerpt(path, max_words=3) == ("one two three", True)


def test_read_document_excerpt_returns_a_short_document_whole(tmp_path: Path) -> None:
    path = tmp_path / "short.txt"
    path.write_text("one  two\nthree", encoding="utf-8")

    assert read_document_excerpt(path, max_words=3) == ("one two three", False)


def test_read_document_excerpt_propagates_parsing_errors(mocker: MockerFixture) -> None:
    mocker.patch("tools.summary_tools.extract_document_text", side_effect=ParsingError("unreadable"))

    with pytest.raises(ParsingError):
        read_document_excerpt(Path("x.pdf"), max_words=10)


def test_summarize_text_caps_model_calls_on_a_very_long_document(mocker: MockerFixture) -> None:
    provider = mocker.Mock()
    provider.complete.return_value = "short summary"
    words = SAFE_PROMPT_WORD_LIMIT * (MAX_SUMMARY_PARTS * 5)
    text = " ".join(f"w{i}" for i in range(words))

    result = summarize_text(text, provider)

    # MAX_SUMMARY_PARTS part summaries, then one summary of those.
    assert provider.complete.call_count == MAX_SUMMARY_PARTS + 1
    assert "evenly spaced sections" in result


def test_evenly_spaced_keeps_the_first_and_last_parts() -> None:
    parts = [str(i) for i in range(10)]

    assert _evenly_spaced(parts, 4) == ["0", "3", "6", "9"]
