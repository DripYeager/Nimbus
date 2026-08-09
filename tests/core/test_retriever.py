from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pytest_mock import MockerFixture

from core.embedder import Embedder, get_embedder
from core.indexer import Indexer
from core.retriever import DEFAULT_TOP_K, Retriever
from core.vector_store import VectorStore
from models.schema import ParsedDocument, SearchResult


def test_retrieve_embeds_the_query_and_passes_filters_to_the_store(mocker: MockerFixture) -> None:
    store = mocker.Mock(spec=VectorStore)
    store.search.return_value = []
    embedder = mocker.Mock(spec=Embedder)
    embedder.embed.return_value = [[0.1, 0.2, 0.3]]

    cutoff = datetime(2026, 6, 1)
    Retriever(store, embedder).retrieve("find the invoice", top_k=3, file_type="pdf", modified_after=cutoff)

    embedder.embed.assert_called_once_with(["find the invoice"])
    store.search.assert_called_once_with([0.1, 0.2, 0.3], top_k=3, file_type="pdf", modified_after=cutoff)


def test_retrieve_uses_the_default_top_k_when_not_specified(mocker: MockerFixture) -> None:
    store = mocker.Mock(spec=VectorStore)
    store.search.return_value = []
    embedder = mocker.Mock(spec=Embedder)
    embedder.embed.return_value = [[0.1, 0.2, 0.3]]

    Retriever(store, embedder).retrieve("find the invoice")

    assert store.search.call_args.kwargs["top_k"] == DEFAULT_TOP_K


def test_retrieve_returns_whatever_the_store_returns(mocker: MockerFixture) -> None:
    store = mocker.Mock(spec=VectorStore)
    expected = [SearchResult(chunk_text="t", file_path="p", file_name="n", score=0.5, metadata={})]
    store.search.return_value = expected
    embedder = mocker.Mock(spec=Embedder)
    embedder.embed.return_value = [[0.1, 0.2, 0.3]]

    assert Retriever(store, embedder).retrieve("anything") == expected


def test_retrieve_finds_the_most_relevant_chunk_end_to_end(tmp_path: Path, mocker: MockerFixture) -> None:
    mocker.patch(
        "core.document_parser.parse_document",
        side_effect=lambda path: ParsedDocument(
            markdown_text="The vendor contract requires thirty days notice for termination."
            if path.name == "contract.txt"
            else "The lunch menu today includes soup and a sandwich.",
            needs_ocr=False,
        ),
    )
    (tmp_path / "contract.txt").write_text("placeholder")
    (tmp_path / "menu.txt").write_text("placeholder")

    store = VectorStore(db_path=tmp_path / "index")
    store.connect()
    Indexer(store, get_embedder()).index_directory(tmp_path)

    results = Retriever(store, get_embedder()).retrieve("What does the contract say about termination?", top_k=1)

    assert len(results) == 1
    assert results[0].file_name == "contract.txt"
