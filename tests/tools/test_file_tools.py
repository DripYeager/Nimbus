from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from core.exceptions import QueryError
from core.retriever import Retriever
from models.schema import CatalogMatch, SearchResult, SourceRef
from tools.file_tools import (
    CHUNK_OVERSAMPLE_FACTOR,
    find_files,
    get_metadata,
    page_label,
    rank_unique_files,
    source_ref_for,
    source_ref_for_match,
)


def _chunk(file_path: str, score: float) -> SearchResult:
    return SearchResult(
        chunk_id=f"{file_path}:{score}",
        chunk_text="x",
        file_path=file_path,
        file_name=Path(file_path).name,
        score=score,
        metadata={},
    )


@pytest.fixture
def retriever(mocker: MockerFixture) -> Mock:
    return mocker.Mock(spec=Retriever)


def test_find_files_returns_one_entry_per_file_best_first(retriever: Mock) -> None:
    retriever.retrieve.return_value = [_chunk("C:/a.txt", 0.5), _chunk("C:/a.txt", 0.2), _chunk("C:/b.txt", 0.8)]

    results = find_files(retriever, "query")

    assert [(r.file_path, r.score) for r in results] == [("C:/b.txt", 0.8), ("C:/a.txt", 0.5)]


def test_find_files_oversamples_chunks_before_deduplicating(retriever: Mock) -> None:
    retriever.retrieve.return_value = []

    find_files(retriever, "query", top_k=3)

    retriever.retrieve.assert_called_once_with("query", top_k=3 * CHUNK_OVERSAMPLE_FACTOR)


def test_find_files_truncates_to_top_k_files(retriever: Mock) -> None:
    retriever.retrieve.return_value = [_chunk(f"C:/{i}.txt", i / 10) for i in range(5)]

    assert len(find_files(retriever, "query", top_k=2)) == 2


def test_find_files_returns_empty_when_nothing_matches(retriever: Mock) -> None:
    retriever.retrieve.return_value = []

    assert find_files(retriever, "query") == []


def test_rank_unique_files_keeps_every_distinct_file() -> None:
    chunks = [_chunk(f"C:/{i}.txt", 0.1) for i in range(12)]

    assert len(rank_unique_files(chunks)) == 12


def test_rank_unique_files_returns_empty_for_no_chunks() -> None:
    assert rank_unique_files([]) == []


def test_get_metadata_returns_size_and_timestamps(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hello", encoding="utf-8")
    os.utime(path, (1_700_000_000, 1_700_000_000))

    metadata = get_metadata(path)

    assert metadata.size_bytes == 5
    assert metadata.file_name == "notes.txt"
    assert metadata.modified_at == datetime.fromtimestamp(1_700_000_000)


def test_get_metadata_returns_none_for_a_missing_file(tmp_path: Path) -> None:
    assert get_metadata(tmp_path / "does-not-exist.txt") is None


def test_get_metadata_raises_query_error_when_the_file_cannot_be_read(tmp_path: Path, mocker: MockerFixture) -> None:
    mocker.patch.object(Path, "stat", side_effect=PermissionError("denied"))

    with pytest.raises(QueryError, match="denied"):
        get_metadata(tmp_path / "locked.txt")


def test_source_ref_for_points_at_the_file() -> None:
    assert source_ref_for(Path("C:/Docs/a.pdf")) == SourceRef(
        file_name="a.pdf", file_path=str(Path("C:/Docs/a.pdf")), score=1.0
    )


def test_source_ref_for_match_keeps_the_match_score() -> None:
    match = CatalogMatch(
        file_path="C:/a.pdf", file_name="a.pdf", size_bytes=1, modified_at=datetime(2026, 1, 1), score=88.0
    )

    assert source_ref_for_match(match) == SourceRef(file_name="a.pdf", file_path="C:/a.pdf", score=88.0)


def test_page_label_names_a_known_page() -> None:
    assert (page_label(12), page_label(None)) == (" (p. 12)", "")
