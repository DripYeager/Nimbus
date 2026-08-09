from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from core.embedder import get_embedder
from core.exceptions import QueryError
from core.indexer import Indexer
from core.query_engine import APP_LAUNCH_NOT_AVAILABLE_MESSAGE, QueryEngine
from core.retriever import Retriever
from core.vector_store import VectorStore
from llm.provider import LLMProvider
from models.schema import FileMetadata, Intent, ParsedDocument, SearchResult, SourceRef


def _chunk(file_path: str, file_name: str, score: float = 0.1) -> SearchResult:
    return SearchResult(chunk_text="x", file_path=file_path, file_name=file_name, score=score, metadata={})


def _engine(mocker: MockerFixture, store_count: int = 10) -> tuple[QueryEngine, LLMProvider, Retriever, VectorStore]:
    provider = mocker.Mock(spec=LLMProvider)
    retriever = mocker.Mock(spec=Retriever)
    store = mocker.Mock(spec=VectorStore)
    store.count.return_value = store_count
    return QueryEngine(retriever, provider, store), provider, retriever, store


def test_file_search_never_calls_the_llm(mocker: MockerFixture) -> None:
    engine, provider, _, _ = _engine(mocker)
    mocker.patch("tools.file_tools.find_files", return_value=[SourceRef(file_name="invoice.pdf", file_path="C:/invoice.pdf", score=0.1)])

    response = engine.handle_query("find the invoice pdf")

    assert response.intent == Intent.FILE_SEARCH
    assert response.used_llm is False
    assert "invoice.pdf" in response.answer
    provider.complete.assert_not_called()


def test_file_search_reports_when_the_index_is_completely_empty(mocker: MockerFixture) -> None:
    engine, _, _, _ = _engine(mocker, store_count=0)
    mocker.patch("tools.file_tools.find_files", return_value=[])

    response = engine.handle_query("find the invoice pdf")

    assert "Nothing has been indexed yet" in response.answer


def test_file_search_reports_no_match_when_the_index_is_not_empty(mocker: MockerFixture) -> None:
    engine, _, _, _ = _engine(mocker, store_count=42)
    mocker.patch("tools.file_tools.find_files", return_value=[])

    response = engine.handle_query("find the invoice pdf")

    assert response.answer == "I couldn't find anything relevant to that."


def test_metadata_never_calls_the_llm(mocker: MockerFixture) -> None:
    engine, provider, _, _ = _engine(mocker)
    mocker.patch(
        "tools.file_tools.find_files",
        return_value=[SourceRef(file_name="budget.xlsx", file_path="C:/budget.xlsx", score=0.1)],
    )
    mocker.patch(
        "tools.file_tools.get_metadata",
        return_value=FileMetadata(
            file_path="C:/budget.xlsx",
            file_name="budget.xlsx",
            size_bytes=2048,
            created_at=datetime(2026, 1, 1),
            modified_at=datetime(2026, 8, 1),
        ),
    )

    response = engine.handle_query("when did I last edit budget.xlsx")

    assert response.intent == Intent.METADATA
    assert response.used_llm is False
    assert "budget.xlsx" in response.answer
    provider.complete.assert_not_called()


def test_metadata_reports_when_the_matched_file_no_longer_exists(mocker: MockerFixture) -> None:
    engine, _, _, _ = _engine(mocker)
    mocker.patch(
        "tools.file_tools.find_files", return_value=[SourceRef(file_name="gone.txt", file_path="C:/gone.txt", score=0.1)]
    )
    mocker.patch("tools.file_tools.get_metadata", return_value=None)

    response = engine.handle_query("when was gone.txt created")

    assert "no longer exists" in response.answer
    assert response.used_llm is False


def test_app_launch_reports_not_available_with_no_llm(mocker: MockerFixture) -> None:
    engine, provider, _, _ = _engine(mocker)

    response = engine.handle_query("open spotify")

    assert response.intent == Intent.APP_LAUNCH
    assert response.used_llm is False
    assert response.answer == APP_LAUNCH_NOT_AVAILABLE_MESSAGE
    provider.complete.assert_not_called()


def test_downloads_today_used_llm_true_when_the_tool_calls_the_provider(mocker: MockerFixture) -> None:
    engine, _, _, _ = _engine(mocker)

    def fake_summarize(tracked_provider: LLMProvider) -> str:
        tracked_provider.complete("irrelevant prompt")
        return "digest of downloads"

    mocker.patch("tools.summary_tools.summarize_todays_downloads", side_effect=fake_summarize)

    response = engine.handle_query("what did I download today")

    assert response.answer == "digest of downloads"
    assert response.used_llm is True


def test_downloads_today_used_llm_false_when_the_tool_short_circuits(mocker: MockerFixture) -> None:
    engine, provider, _, _ = _engine(mocker)
    mocker.patch("tools.summary_tools.summarize_todays_downloads", return_value="No files were downloaded today.")

    response = engine.handle_query("what did I download today")

    assert response.answer == "No files were downloaded today."
    assert response.used_llm is False
    provider.complete.assert_not_called()


def test_handle_downloads_today_used_llm_true_when_the_tool_calls_the_provider(mocker: MockerFixture) -> None:
    engine, _, _, _ = _engine(mocker)

    def fake_summarize(tracked_provider: LLMProvider) -> str:
        tracked_provider.complete("irrelevant prompt")
        return "digest of downloads"

    mocker.patch("tools.summary_tools.summarize_todays_downloads", side_effect=fake_summarize)

    response = engine.handle_downloads_today()

    assert response.intent == Intent.DOWNLOADS_TODAY
    assert response.answer == "digest of downloads"
    assert response.used_llm is True
    assert response.sources == []


def test_handle_downloads_today_used_llm_false_when_the_tool_short_circuits(mocker: MockerFixture) -> None:
    engine, provider, _, _ = _engine(mocker)
    mocker.patch("tools.summary_tools.summarize_todays_downloads", return_value="No files were downloaded today.")

    response = engine.handle_downloads_today()

    assert response.answer == "No files were downloaded today."
    assert response.used_llm is False
    provider.complete.assert_not_called()


def test_handle_downloads_today_skips_intent_classification(mocker: MockerFixture) -> None:
    """No text is ever classified — the intent is fixed by calling this entry point at all."""
    engine, provider, _, _ = _engine(mocker)
    mocker.patch("tools.summary_tools.summarize_todays_downloads", return_value="No files were downloaded today.")
    classify_spy = mocker.patch("core.query_engine.classify_intent")

    engine.handle_downloads_today()

    classify_spy.assert_not_called()
    provider.complete.assert_not_called()


def test_summarize_used_llm_true_when_a_matching_file_is_found(mocker: MockerFixture) -> None:
    engine, _, _, _ = _engine(mocker)
    mocker.patch(
        "tools.file_tools.find_files", return_value=[SourceRef(file_name="q3.pdf", file_path="C:/q3.pdf", score=0.1)]
    )

    def fake_summarize(path: Path, tracked_provider: LLMProvider) -> str:
        tracked_provider.complete("irrelevant prompt")
        return "five bullet points"

    mocker.patch("tools.summary_tools.summarize_document", side_effect=fake_summarize)

    response = engine.handle_query("summarize the Q3 report")

    assert response.answer == "five bullet points"
    assert response.used_llm is True
    assert response.sources[0].file_name == "q3.pdf"


def test_summarize_used_llm_false_when_no_matching_file_is_found(mocker: MockerFixture) -> None:
    engine, provider, _, _ = _engine(mocker)
    mocker.patch("tools.file_tools.find_files", return_value=[])

    response = engine.handle_query("summarize the Q3 report")

    assert response.used_llm is False
    provider.complete.assert_not_called()


def test_general_qa_used_llm_true_and_returns_the_synthesized_answer(mocker: MockerFixture) -> None:
    engine, provider, retriever, _ = _engine(mocker)
    provider.complete.return_value = "Termination requires 30 days notice."
    retriever.retrieve.return_value = [_chunk("C:/contract.pdf", "contract.pdf")]

    response = engine.handle_query("what does the contract say about termination")

    assert response.intent == Intent.GENERAL_QA
    assert response.answer == "Termination requires 30 days notice."
    assert response.used_llm is True
    assert response.sources[0].file_name == "contract.pdf"


def test_general_qa_used_llm_false_when_nothing_is_retrieved(mocker: MockerFixture) -> None:
    engine, provider, retriever, _ = _engine(mocker)
    retriever.retrieve.return_value = []

    response = engine.handle_query("what does the contract say about termination")

    assert response.used_llm is False
    provider.complete.assert_not_called()


def test_used_llm_stays_false_when_only_intent_classification_needed_the_llm(mocker: MockerFixture) -> None:
    """Classification's own LLM fallback must never count toward the cost-control used_llm flag."""
    engine, provider, _, _ = _engine(mocker)
    provider.complete.return_value = "file_search"  # only ever consumed by the classification fallback
    mocker.patch(
        "tools.file_tools.find_files", return_value=[SourceRef(file_name="a.txt", file_path="C:/a.txt", score=0.1)]
    )

    response = engine.handle_query("the vendor contract")  # no keyword matches -> LLM classifies it

    assert response.intent == Intent.FILE_SEARCH
    assert response.used_llm is False
    provider.complete.assert_called_once()  # the one classification call, nothing from the route handler


def test_handle_query_reports_a_non_negative_integer_elapsed_time(mocker: MockerFixture) -> None:
    engine, _, _, _ = _engine(mocker, store_count=0)
    mocker.patch("tools.file_tools.find_files", return_value=[])

    response = engine.handle_query("find something")

    assert isinstance(response.elapsed_ms, int)
    assert response.elapsed_ms >= 0


def test_route_raises_query_error_for_an_unrecognized_intent(mocker: MockerFixture) -> None:
    engine, provider, _, _ = _engine(mocker)
    with pytest.raises(QueryError):
        engine._route("text", "not_a_real_intent", provider)


def test_handle_query_works_end_to_end_with_real_retrieval(tmp_path: Path, mocker: MockerFixture) -> None:
    mocker.patch(
        "core.document_parser.parse_document",
        return_value=ParsedDocument(
            markdown_text="The vendor contract requires thirty days notice for termination.", needs_ocr=False
        ),
    )
    (tmp_path / "contract.txt").write_text("placeholder")

    store = VectorStore(db_path=tmp_path / "index")
    store.connect()
    Indexer(store, get_embedder()).index_directory(tmp_path)
    retriever = Retriever(store, get_embedder())
    provider = mocker.Mock(spec=LLMProvider)

    engine = QueryEngine(retriever, provider, store)
    response = engine.handle_query("find the contract")

    assert response.intent == Intent.FILE_SEARCH
    assert response.used_llm is False
    assert any(source.file_name == "contract.txt" for source in response.sources)
