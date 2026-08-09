from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from core.exceptions import IndexingError
from core.vector_store import VectorStore
from models.schema import IndexedChunk


def _make_chunk(file_path: str, chunk_index: int = 0, content_hash: str = "hash-a") -> IndexedChunk:
    now = datetime(2026, 1, 1, 12, 0, 0)
    return IndexedChunk(
        id=f"{file_path}:{chunk_index}",
        file_path=file_path,
        file_name=Path(file_path).name,
        file_type="txt",
        content_hash=content_hash,
        chunk_index=chunk_index,
        chunk_text=f"chunk {chunk_index} of {file_path}",
        vector=[0.1, 0.2, 0.3, 0.4],
        created_at=now,
        modified_at=now,
        indexed_at=now,
    )


@pytest.fixture
def store(tmp_path: Path) -> VectorStore:
    vs = VectorStore(db_path=tmp_path / "index")
    vs.connect()
    return vs


def test_count_is_zero_before_anything_is_written(store: VectorStore) -> None:
    assert store.count() == 0


def test_upsert_chunks_then_count_reflects_them(store: VectorStore) -> None:
    store.upsert_chunks([_make_chunk("C:/docs/a.txt", 0), _make_chunk("C:/docs/a.txt", 1)])
    assert store.count() == 2


def test_upsert_chunks_with_empty_list_is_a_no_op(store: VectorStore) -> None:
    store.upsert_chunks([])
    assert store.count() == 0


def test_upsert_chunks_replaces_prior_rows_for_the_same_file(store: VectorStore) -> None:
    store.upsert_chunks([_make_chunk("C:/docs/a.txt", 0), _make_chunk("C:/docs/a.txt", 1)])
    store.upsert_chunks([_make_chunk("C:/docs/a.txt", 0, content_hash="hash-b")])
    assert store.count() == 1


def test_get_by_hash_finds_a_matching_chunk(store: VectorStore) -> None:
    store.upsert_chunks([_make_chunk("C:/docs/a.txt", content_hash="abc123")])
    found = store.get_by_hash("abc123")
    assert found is not None
    assert found.file_path == "C:/docs/a.txt"


def test_get_by_hash_returns_none_when_nothing_matches(store: VectorStore) -> None:
    assert store.get_by_hash("does-not-exist") is None


def test_search_returns_the_nearest_chunks(store: VectorStore) -> None:
    store.upsert_chunks([_make_chunk("C:/docs/a.txt", 0), _make_chunk("C:/docs/b.txt", 0)])
    results = store.search([0.1, 0.2, 0.3, 0.4], top_k=1)
    assert len(results) == 1
    assert results[0].file_name in {"a.txt", "b.txt"}


def test_search_returns_empty_list_before_anything_is_indexed(store: VectorStore) -> None:
    assert store.search([0.1, 0.2, 0.3, 0.4]) == []


def test_reconnecting_to_an_existing_db_picks_up_its_table(tmp_path: Path) -> None:
    db_path = tmp_path / "index"
    first = VectorStore(db_path=db_path)
    first.connect()
    first.upsert_chunks([_make_chunk("C:/docs/a.txt", content_hash="abc123")])

    second = VectorStore(db_path=db_path)
    second.connect()

    assert second.count() == 1
    assert second.get_by_hash("abc123") is not None
    second.upsert_chunks([_make_chunk("C:/docs/b.txt", content_hash="def456")])
    assert second.count() == 2


def test_delete_by_path_removes_only_that_files_rows(store: VectorStore) -> None:
    store.upsert_chunks([_make_chunk("C:/docs/a.txt", 0), _make_chunk("C:/docs/b.txt", 0)])
    store.delete_by_path("C:/docs/a.txt")
    assert store.count() == 1


def test_connect_raises_indexing_error_when_db_path_is_a_file(tmp_path: Path) -> None:
    blocked_path = tmp_path / "blocked"
    blocked_path.write_text("not a directory")
    with pytest.raises(IndexingError):
        VectorStore(db_path=blocked_path).connect()
