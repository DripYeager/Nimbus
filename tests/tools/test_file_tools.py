from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from core.embedder import get_embedder
from core.exceptions import QueryError
from core.indexer import Indexer
from core.retriever import Retriever
from core.vector_store import VectorStore
from models.schema import ParsedDocument, SearchResult
from tools.file_tools import find_files, get_metadata, list_recent, rank_unique_files


def _chunk(file_path: str, file_name: str, score: float) -> SearchResult:
    return SearchResult(chunk_text="x", file_path=file_path, file_name=file_name, score=score, metadata={})


def test_find_files_deduplicates_to_one_entry_per_file(mocker: MockerFixture) -> None:
    retriever = mocker.Mock(spec=Retriever)
    retriever.retrieve.return_value = [
        _chunk("C:/a.txt", "a.txt", score=0.5),
        _chunk("C:/a.txt", "a.txt", score=0.2),
        _chunk("C:/b.txt", "b.txt", score=0.8),
    ]
    results = find_files(retriever, "query", top_k=5)
    assert [r.file_path for r in results] == ["C:/a.txt", "C:/b.txt"]


def test_find_files_ranks_lowest_score_first(mocker: MockerFixture) -> None:
    retriever = mocker.Mock(spec=Retriever)
    retriever.retrieve.return_value = [
        _chunk("C:/high-distance.txt", "high-distance.txt", score=0.9),
        _chunk("C:/low-distance.txt", "low-distance.txt", score=0.1),
    ]
    results = find_files(retriever, "query")
    assert [r.file_path for r in results] == ["C:/low-distance.txt", "C:/high-distance.txt"]


def test_find_files_returns_empty_list_when_nothing_matches(mocker: MockerFixture) -> None:
    retriever = mocker.Mock(spec=Retriever)
    retriever.retrieve.return_value = []
    assert find_files(retriever, "query") == []


def test_find_files_oversamples_chunks_before_deduplicating(mocker: MockerFixture) -> None:
    retriever = mocker.Mock(spec=Retriever)
    retriever.retrieve.return_value = []
    find_files(retriever, "query", top_k=5)
    retriever.retrieve.assert_called_once_with("query", top_k=20)


def test_find_files_truncates_to_top_k_distinct_files(mocker: MockerFixture) -> None:
    retriever = mocker.Mock(spec=Retriever)
    retriever.retrieve.return_value = [_chunk(f"C:/{i}.txt", f"{i}.txt", score=float(i)) for i in range(10)]
    results = find_files(retriever, "query", top_k=3)
    assert len(results) == 3
    assert [r.file_path for r in results] == ["C:/0.txt", "C:/1.txt", "C:/2.txt"]


def test_rank_unique_files_returns_every_distinct_file_without_truncating() -> None:
    chunks = [
        _chunk("C:/a.txt", "a.txt", score=0.5),
        _chunk("C:/a.txt", "a.txt", score=0.2),
        _chunk("C:/b.txt", "b.txt", score=0.9),
        _chunk("C:/c.txt", "c.txt", score=0.1),
    ]
    results = rank_unique_files(chunks)
    assert [r.file_path for r in results] == ["C:/c.txt", "C:/a.txt", "C:/b.txt"]


def test_rank_unique_files_returns_empty_list_for_no_chunks() -> None:
    assert rank_unique_files([]) == []


def test_find_files_ranks_real_indexed_files_end_to_end(tmp_path: Path, mocker: MockerFixture) -> None:
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
    retriever = Retriever(store, get_embedder())

    results = find_files(retriever, "What does the contract say about termination?", top_k=1)

    assert len(results) == 1
    assert results[0].file_name == "contract.txt"


def test_get_metadata_returns_size_and_timestamps(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hello world")

    metadata = get_metadata(path)

    assert metadata is not None
    assert metadata.file_name == "notes.txt"
    assert metadata.size_bytes == len(b"hello world")
    assert isinstance(metadata.modified_at, datetime)


def test_get_metadata_returns_none_for_a_missing_file(tmp_path: Path) -> None:
    assert get_metadata(tmp_path / "does-not-exist.txt") is None


def test_get_metadata_raises_query_error_on_a_permission_error(tmp_path: Path, mocker: MockerFixture) -> None:
    path = tmp_path / "locked.txt"
    path.write_text("x")
    mocker.patch.object(Path, "stat", side_effect=PermissionError("access denied"))
    with pytest.raises(QueryError):
        get_metadata(path)


def test_list_recent_returns_only_files_modified_after_the_cutoff(tmp_path: Path) -> None:
    old_file = tmp_path / "old.txt"
    new_file = tmp_path / "new.txt"
    old_file.write_text("x")
    new_file.write_text("x")
    _set_mtime(old_file, datetime(2026, 1, 1))
    _set_mtime(new_file, datetime(2026, 8, 1))

    results = list_recent(tmp_path, modified_after=datetime(2026, 6, 1))

    assert [m.file_name for m in results] == ["new.txt"]


def test_list_recent_sorts_most_recently_modified_first(tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("x")
    second.write_text("x")
    _set_mtime(first, datetime(2026, 8, 1))
    _set_mtime(second, datetime(2026, 8, 5))

    results = list_recent(tmp_path, modified_after=datetime(2026, 1, 1))

    assert [m.file_name for m in results] == ["second.txt", "first.txt"]


def test_list_recent_respects_the_limit(tmp_path: Path) -> None:
    for i in range(5):
        path = tmp_path / f"file{i}.txt"
        path.write_text("x")
        _set_mtime(path, datetime(2026, 8, 1 + i))

    results = list_recent(tmp_path, modified_after=datetime(2026, 1, 1), limit=2)

    assert len(results) == 2


def test_list_recent_ignores_subdirectories(tmp_path: Path) -> None:
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.txt").write_text("x")
    top_level = tmp_path / "top.txt"
    top_level.write_text("x")
    _set_mtime(top_level, datetime(2026, 8, 1))

    results = list_recent(tmp_path, modified_after=datetime(2026, 1, 1))

    assert [m.file_name for m in results] == ["top.txt"]


def test_list_recent_raises_query_error_for_a_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(QueryError):
        list_recent(tmp_path / "does-not-exist", modified_after=datetime(2026, 1, 1))


def _set_mtime(path: Path, when: datetime) -> None:
    timestamp = when.timestamp()
    os.utime(path, (timestamp, timestamp))
