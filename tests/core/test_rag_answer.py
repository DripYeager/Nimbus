from __future__ import annotations

from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from core.exceptions import ProviderError, QueryError
from core.rag_answer import NOTHING_FOUND_MESSAGE, RagAnswerer
from core.retriever import Retriever
from llm.provider import LLMProvider
from models.schema import SearchResult


def _chunk(chunk_id: str, file_path: str, score: float, text: str = "excerpt") -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        chunk_text=text,
        file_path=file_path,
        file_name=file_path.split("/")[-1],
        score=score,
        metadata={},
    )


@pytest.fixture
def retriever(mocker: MockerFixture) -> Mock:
    return mocker.Mock(spec=Retriever)


@pytest.fixture
def provider(mocker: MockerFixture) -> Mock:
    provider = mocker.Mock(spec=LLMProvider)
    provider.stream.return_value = iter(["Thirty ", "days."])
    return provider


def test_answer_streams_a_grounded_answer(retriever: Mock, provider: Mock) -> None:
    retriever.retrieve.return_value = [_chunk("1", "C:/contract.pdf", 0.9, "Notice is 30 days.")]

    tokens, _ = RagAnswerer(retriever, provider).answer("What's the notice period?")

    assert "".join(tokens) == "Thirty days."
    prompt = provider.stream.call_args.args[0]
    assert "Notice is 30 days." in prompt
    assert "What's the notice period?" in prompt


def test_answer_returns_one_source_per_file_best_first(retriever: Mock, provider: Mock) -> None:
    retriever.retrieve.return_value = [
        _chunk("1", "C:/a.txt", 0.2),
        _chunk("2", "C:/b.txt", 0.8),
        _chunk("3", "C:/a.txt", 0.5),
    ]

    _, sources = RagAnswerer(retriever, provider).answer("q")

    assert [(s.file_path, s.score) for s in sources] == [("C:/b.txt", 0.8), ("C:/a.txt", 0.5)]


def test_answer_skips_the_model_when_nothing_is_found(retriever: Mock, provider: Mock) -> None:
    retriever.retrieve.return_value = []

    tokens, sources = RagAnswerer(retriever, provider).answer("q")

    assert list(tokens) == [NOTHING_FOUND_MESSAGE]
    assert sources == []
    provider.stream.assert_not_called()


def test_answer_propagates_retrieval_errors(retriever: Mock, provider: Mock) -> None:
    retriever.retrieve.side_effect = QueryError("index unavailable")

    with pytest.raises(QueryError):
        RagAnswerer(retriever, provider).answer("q")


def test_answer_propagates_provider_errors(retriever: Mock, provider: Mock) -> None:
    retriever.retrieve.return_value = [_chunk("1", "C:/a.txt", 0.5)]
    provider.stream.side_effect = ProviderError("offline")

    with pytest.raises(ProviderError):
        RagAnswerer(retriever, provider).answer("q")
