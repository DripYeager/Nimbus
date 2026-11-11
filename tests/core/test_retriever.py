from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from core.embedder import Embedder
from core.exceptions import QueryError
from core.reranker import Reranker
from core.retriever import CANDIDATE_MULTIPLIER, RERANK_POOL, RRF_K, Retriever, fuse_rankings
from core.vector_store import VectorStore
from models.schema import IndexedChunk, SearchResult

QUERY_VECTOR = [1.0, 0.0, 0.0, 0.0]


def _result(chunk_id: str, modified_at: datetime = datetime(2026, 1, 1)) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        chunk_text=f"text of {chunk_id}",
        file_path=f"C:\\Docs\\{chunk_id}.txt",
        file_name=f"{chunk_id}.txt",
        score=0.0,
        metadata={"modified_at": modified_at},
    )


@pytest.fixture
def store(mocker: MockerFixture) -> Mock:
    fake = mocker.Mock(spec=VectorStore)
    fake.search.return_value = []
    fake.search_text.return_value = []
    return fake


@pytest.fixture
def embedder(mocker: MockerFixture) -> Mock:
    fake = mocker.Mock(spec=Embedder)
    fake.embed_query.return_value = QUERY_VECTOR
    return fake


def test_fuse_rankings_ranks_a_chunk_found_by_both_lists_first() -> None:
    semantic = [_result("only-semantic"), _result("both")]
    keyword = [_result("only-keyword"), _result("both")]

    fused = fuse_rankings([semantic, keyword])

    assert fused[0].chunk_id == "both"


def test_fuse_rankings_scores_with_reciprocal_rank() -> None:
    fused = fuse_rankings([[_result("a"), _result("b")], [_result("a")]])

    assert [r.score for r in fused] == [2 / (RRF_K + 1), 1 / (RRF_K + 2)]


def test_fuse_rankings_returns_each_chunk_once() -> None:
    fused = fuse_rankings([[_result("a")], [_result("a")], [_result("a")]])

    assert [r.chunk_id for r in fused] == ["a"]


def test_fuse_rankings_returns_empty_for_empty_rankings() -> None:
    assert fuse_rankings([[], []]) == []


def test_retrieve_oversamples_both_searches(store: Mock, embedder: Mock) -> None:
    Retriever(store, embedder).retrieve("INV-2231", top_k=2)

    store.search.assert_called_once_with(QUERY_VECTOR, top_k=2 * CANDIDATE_MULTIPLIER, modified_after=None)
    store.search_text.assert_called_once_with("INV-2231", top_k=2 * CANDIDATE_MULTIPLIER)


def test_retrieve_returns_at_most_top_k_results(store: Mock, embedder: Mock) -> None:
    store.search.return_value = [_result(str(i)) for i in range(6)]

    assert len(Retriever(store, embedder).retrieve("invoice", top_k=2)) == 2


def test_retrieve_puts_a_keyword_and_meaning_match_on_top(store: Mock, embedder: Mock) -> None:
    store.search.return_value = [_result("similar"), _result("exact")]
    store.search_text.return_value = [_result("exact")]

    assert Retriever(store, embedder).retrieve("INV-2231")[0].chunk_id == "exact"


def test_retrieve_drops_keyword_hits_older_than_modified_after(store: Mock, embedder: Mock) -> None:
    store.search_text.return_value = [_result("old", datetime(2025, 1, 1)), _result("new", datetime(2026, 9, 1))]

    results = Retriever(store, embedder).retrieve("INV-2231", modified_after=datetime(2026, 6, 1))

    assert [r.chunk_id for r in results] == ["new"]


def test_retrieve_passes_the_recency_filter_to_vector_search(store: Mock, embedder: Mock) -> None:
    cutoff = datetime(2026, 6, 1)

    Retriever(store, embedder).retrieve("invoice", modified_after=cutoff)

    assert store.search.call_args.kwargs["modified_after"] == cutoff


def test_retrieve_lets_a_vector_search_failure_propagate(store: Mock, embedder: Mock) -> None:
    store.search.side_effect = QueryError("store unavailable")

    with pytest.raises(QueryError):
        Retriever(store, embedder).retrieve("invoice")


def test_retrieve_semantic_only_skips_keyword_search(store: Mock, embedder: Mock) -> None:
    store.search.return_value = [_result("a")]

    results = Retriever(store, embedder).retrieve_semantic_only("invoice", top_k=3)

    assert [r.chunk_id for r in results] == ["a"]
    store.search.assert_called_once_with(QUERY_VECTOR, top_k=3)
    store.search_text.assert_not_called()


def test_retrieve_finds_an_exact_token_in_a_real_store(tmp_path: Path, embedder: Mock) -> None:
    store = VectorStore(db_path=tmp_path / "index")
    store.connect()
    now = datetime(2026, 1, 1)
    store.upsert_chunks(
        [
            IndexedChunk(
                id=name,
                file_path=f"C:\\Docs\\{name}.txt",
                file_name=f"{name}.txt",
                file_type="txt",
                content_hash="h",
                chunk_index=0,
                chunk_text=text,
                vector=vector,
                created_at=now,
                modified_at=now,
                indexed_at=now,
            )
            for name, text, vector in [
                ("lookalike", "Invoices are due within thirty days", QUERY_VECTOR),
                ("target", "Invoice INV-2231 for the March delivery", [0.0, 1.0, 0.0, 0.0]),
            ]
        ]
    )

    results = Retriever(store, embedder).retrieve("INV-2231", top_k=1)

    assert [r.chunk_id for r in results] == ["target"]


def test_retrieve_hands_a_wider_pool_to_a_ready_reranker(store: Mock, embedder: Mock, mocker: MockerFixture) -> None:
    store.search.return_value = [_result(f"c{i}") for i in range(30)]
    reranker = mocker.Mock(spec=Reranker)
    reranker.is_ready.return_value = True
    reranker.rerank.side_effect = lambda query, pool, top_k: pool[:top_k]

    Retriever(store, embedder, reranker).retrieve("q", top_k=5)

    query, pool, top_k = reranker.rerank.call_args.args
    assert (query, len(pool), top_k) == ("q", RERANK_POOL, 5)


def test_retrieve_skips_a_reranker_that_is_not_ready(store: Mock, embedder: Mock, mocker: MockerFixture) -> None:
    reranker = mocker.Mock(spec=Reranker)
    reranker.is_ready.return_value = False

    Retriever(store, embedder, reranker).retrieve("q", top_k=5)

    reranker.rerank.assert_not_called()


def test_retrieve_skips_keyword_search_for_a_natural_question(store: Mock, embedder: Mock) -> None:
    Retriever(store, embedder).retrieve("how much did we pay for the desks")

    store.search_text.assert_not_called()


def test_retrieve_uses_the_given_keyword_weighting(store: Mock, embedder: Mock) -> None:
    Retriever(store, embedder, keyword_weighting=lambda _query: 1.0).retrieve("how much did we pay")

    store.search_text.assert_called_once()


def test_fuse_rankings_ignores_a_ranking_weighted_zero() -> None:
    meaning, keyword = [_result("a"), _result("b")], [_result("b")]

    assert [r.chunk_id for r in fuse_rankings([meaning, keyword], [1.0, 0.0])] == ["a", "b"]


def test_fuse_rankings_lets_a_heavier_ranking_win() -> None:
    meaning, keyword = [_result("a"), _result("b")], [_result("b"), _result("a")]

    assert fuse_rankings([meaning, keyword], [1.0, 2.0])[0].chunk_id == "b"
