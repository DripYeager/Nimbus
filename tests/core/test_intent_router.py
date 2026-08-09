from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from core.intent_router import classify_intent
from llm.provider import LLMProvider
from models.schema import Intent


def _failing_provider(mocker: MockerFixture) -> LLMProvider:
    """A provider that blows up if called — proves a keyword-path test never reaches the LLM."""
    provider = mocker.Mock(spec=LLMProvider)
    provider.complete.side_effect = AssertionError("keyword rule should have matched before the LLM fallback")
    return provider


@pytest.mark.parametrize(
    "text",
    ["find the invoice pdf", "where is my resume", "which file has the budget"],
)
def test_classify_intent_routes_file_search_by_keyword(text: str, mocker: MockerFixture) -> None:
    assert classify_intent(text, provider=_failing_provider(mocker)) == Intent.FILE_SEARCH


@pytest.mark.parametrize(
    "text",
    ["when did I last edit budget.xlsx", "how big is this file", "when was this created"],
)
def test_classify_intent_routes_metadata_by_keyword(text: str, mocker: MockerFixture) -> None:
    assert classify_intent(text, provider=_failing_provider(mocker)) == Intent.METADATA


@pytest.mark.parametrize(
    "text",
    ["open spotify", "launch vs code", "start the installer", "run the setup wizard"],
)
def test_classify_intent_routes_app_launch_by_keyword(text: str, mocker: MockerFixture) -> None:
    assert classify_intent(text, provider=_failing_provider(mocker)) == Intent.APP_LAUNCH


@pytest.mark.parametrize(
    "text",
    ["what did I download today", "check my downloads today", "what got downloaded today"],
)
def test_classify_intent_routes_downloads_today_by_keyword(text: str, mocker: MockerFixture) -> None:
    assert classify_intent(text, provider=_failing_provider(mocker)) == Intent.DOWNLOADS_TODAY


@pytest.mark.parametrize(
    "text",
    ["summarize the Q3 report", "give me the tl;dr", "just the key points please", "brief me on this"],
)
def test_classify_intent_routes_summarize_by_keyword(text: str, mocker: MockerFixture) -> None:
    assert classify_intent(text, provider=_failing_provider(mocker)) == Intent.SUMMARIZE


@pytest.mark.parametrize(
    "text",
    ["what does the contract say about termination", "how does this work", "why did this happen"],
)
def test_classify_intent_routes_general_qa_by_keyword(text: str, mocker: MockerFixture) -> None:
    assert classify_intent(text, provider=_failing_provider(mocker)) == Intent.GENERAL_QA


def test_classify_intent_requires_a_temporal_cue_for_downloads_today(mocker: MockerFixture) -> None:
    provider = mocker.Mock(spec=LLMProvider)
    provider.complete.return_value = "general_qa"
    assert classify_intent("check my downloads", provider=provider) == Intent.GENERAL_QA
    provider.complete.assert_called_once()


def test_classify_intent_does_not_match_run_inside_a_longer_word(mocker: MockerFixture) -> None:
    provider = mocker.Mock(spec=LLMProvider)
    provider.complete.return_value = "general_qa"
    result = classify_intent("the app has been running slowly", provider=provider)
    assert result != Intent.APP_LAUNCH
    provider.complete.assert_called_once()


def test_classify_intent_falls_back_to_the_llm_when_no_keyword_matches(mocker: MockerFixture) -> None:
    provider = mocker.Mock(spec=LLMProvider)
    provider.complete.return_value = "file_search"
    assert classify_intent("the vendor contract", provider=provider) == Intent.FILE_SEARCH
    provider.complete.assert_called_once()


def test_classify_intent_defaults_to_general_qa_when_the_llm_answer_is_unparseable(mocker: MockerFixture) -> None:
    provider = mocker.Mock(spec=LLMProvider)
    provider.complete.return_value = "not a real intent"
    assert classify_intent("the vendor contract", provider=provider) == Intent.GENERAL_QA


def test_classify_intent_uses_the_real_configured_provider_when_none_is_given(mocker: MockerFixture) -> None:
    mocker.patch("llm.ollama_provider.ollama.Client")
    assert classify_intent("find the invoice pdf") == Intent.FILE_SEARCH
