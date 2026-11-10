from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

import config.settings as settings_module
from config.settings import Settings
from core.exceptions import IndexingError, QueryError
from core.vector_store import SCHEMA_VERSION, VectorStore
from models.schema import IndexedChunk

MODEL = "BAAI/bge-small-en-v1.5"
NORTH, EAST, UP = [1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]


def _chunk(
    file_path: str,
    text: str = "some words",
    vector: list[float] | None = None,
    content_hash: str = "hash-a",
    modified_at: datetime = datetime(2026, 1, 1, 12, 0, 0),
) -> IndexedChunk:
    return IndexedChunk(
        id=f"{file_path}:{text}",
        file_path=file_path,
        file_name=Path(file_path).name,
        file_type="txt",
        content_hash=content_hash,
        chunk_index=0,
        chunk_text=text,
        vector=vector or NORTH,
        created_at=modified_at,
        modified_at=modified_at,
        indexed_at=modified_at,
    )


@pytest.fixture
def store(tmp_path: Path) -> VectorStore:
    opened = VectorStore(db_path=tmp_path / "search.db")
    opened.connect()
    return opened


def _paths(store: VectorStore) -> set[str]:
    return {r.file_path for r in store.search(NORTH, top_k=100)}


def test_connect_raises_indexing_error_when_the_folder_is_a_file(tmp_path: Path) -> None:
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")

    with pytest.raises(IndexingError):
        VectorStore(db_path=blocker / "search.db").connect()


def test_vector_store_defaults_to_the_settings_index_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_module, "_settings", Settings(_env_file=None, data_dir=tmp_path))

    VectorStore().connect()

    assert (tmp_path / "search.db").is_file()


def test_count_is_zero_before_anything_is_written(store: VectorStore) -> None:
    assert store.count() == 0


def test_upsert_chunks_with_an_empty_list_is_a_no_op(store: VectorStore) -> None:
    store.upsert_chunks([])

    assert store.count() == 0


def test_upsert_chunks_replaces_every_earlier_row_for_the_same_file(store: VectorStore) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\a.txt", "one"), _chunk("C:\\Docs\\a.txt", "two")])
    store.upsert_chunks([_chunk("C:\\Docs\\b.txt")])

    store.upsert_chunks([_chunk("C:\\Docs\\a.txt", "three", content_hash="hash-b")])

    assert store.count() == 2
    assert store.content_hash_for("C:\\Docs\\a.txt") == "hash-b"


def test_upsert_chunks_raises_indexing_error_for_a_wrong_vector_size(store: VectorStore) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\a.txt")])

    with pytest.raises(IndexingError):
        store.upsert_chunks([_chunk("C:\\Docs\\b.txt", vector=[0.1, 0.2])])


def test_content_hash_for_returns_none_for_an_unknown_file(store: VectorStore) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\a.txt")])

    assert store.content_hash_for("C:\\Docs\\other.txt") is None


def test_content_hash_for_returns_none_before_any_table_exists(store: VectorStore) -> None:
    assert store.content_hash_for("C:\\Docs\\a.txt") is None


def test_content_hash_for_handles_a_path_with_an_apostrophe(store: VectorStore) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\O'Brien.txt", content_hash="quoted")])

    assert store.content_hash_for("C:\\Docs\\O'Brien.txt") == "quoted"


def test_search_returns_the_nearest_chunk_first(store: VectorStore) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\north.txt", vector=NORTH), _chunk("C:\\Docs\\east.txt", vector=EAST)])

    results = store.search(EAST, top_k=2)

    assert [r.file_name for r in results] == ["east.txt", "north.txt"]


def test_search_gives_the_nearest_chunk_the_highest_score(store: VectorStore) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\north.txt", vector=NORTH), _chunk("C:\\Docs\\up.txt", vector=UP)])

    nearest, farther = store.search(NORTH, top_k=2)

    assert nearest.score == pytest.approx(1.0)
    assert nearest.score > farther.score


def test_search_filters_out_chunks_older_than_modified_after(store: VectorStore) -> None:
    store.upsert_chunks(
        [
            _chunk("C:\\Docs\\old.txt", modified_at=datetime(2026, 1, 1)),
            _chunk("C:\\Docs\\new.txt", modified_at=datetime(2026, 8, 1)),
        ]
    )

    results = store.search(NORTH, top_k=5, modified_after=datetime(2026, 6, 1))

    assert [r.file_name for r in results] == ["new.txt"]


def test_search_returns_empty_before_anything_is_indexed(store: VectorStore) -> None:
    assert store.search(NORTH) == []


def test_search_wraps_a_backend_failure_in_query_error(store: VectorStore, mocker: MockerFixture) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\a.txt")])
    store._reader.close()

    with pytest.raises(QueryError):
        store.search(NORTH)


def test_search_text_finds_an_exact_invoice_number(store: VectorStore) -> None:
    store.upsert_chunks(
        [
            _chunk("C:\\Docs\\invoice.txt", "Invoice INV-2231 was paid in March"),
            _chunk("C:\\Docs\\menu.txt", "Soup and sandwiches for lunch"),
        ]
    )

    assert [r.file_name for r in store.search_text("INV-2231")] == ["invoice.txt"]


def test_search_text_finds_rows_added_after_the_table_was_created(store: VectorStore) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\first.txt", "nothing to see")])
    store.upsert_chunks([_chunk("C:\\Docs\\later.txt", "Contract with Okonkwo Ltd")])

    assert [r.file_name for r in store.search_text("Okonkwo")] == ["later.txt"]


def test_search_text_returns_empty_for_a_blank_query(store: VectorStore) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\a.txt")])

    assert store.search_text("   ") == []


def test_search_text_returns_empty_when_the_query_cannot_be_parsed(store: VectorStore, mocker: MockerFixture) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\a.txt")])
    store._reader.close()

    assert store.search_text("words") == []


def test_search_text_treats_query_syntax_as_plain_words(store: VectorStore) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\a.txt", "budget AND forecast (draft)")])

    assert [r.file_name for r in store.search_text('AND OR ( "draft')] == ["a.txt"]


def test_search_text_matches_a_code_exactly_not_just_its_prefix(store: VectorStore) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\a.txt", "Invoice INV-2231"), _chunk("C:\\Docs\\b.txt", "Invoice INV-9999")])

    assert [r.file_name for r in store.search_text("INV-9999")] == ["b.txt"]


def test_delete_by_path_removes_only_that_files_rows(store: VectorStore) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\a.txt"), _chunk("C:\\Docs\\b.txt")])

    store.delete_by_path("C:\\Docs\\a.txt")

    assert _paths(store) == {"C:\\Docs\\b.txt"}


def test_delete_by_path_is_a_no_op_before_any_table_exists(store: VectorStore) -> None:
    store.delete_by_path("C:\\Docs\\a.txt")

    assert store.count() == 0


def test_delete_by_paths_removes_every_listed_file_across_batches(
    store: VectorStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("core.vector_store.DELETE_BATCH_SIZE", 1)
    store.upsert_chunks([_chunk("C:\\Docs\\a.txt"), _chunk("C:\\Docs\\O'b.txt"), _chunk("C:\\Docs\\keep.txt")])

    store.delete_by_paths(["C:\\Docs\\a.txt", "C:\\Docs\\O'b.txt"])

    assert _paths(store) == {"C:\\Docs\\keep.txt"}


def test_delete_under_ignores_case_and_spares_a_same_prefix_sibling(store: VectorStore) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\a.txt"), _chunk("C:\\docs\\Sub\\b.txt"), _chunk("C:\\Docs2\\keep.txt")])

    store.delete_under(Path("C:\\DOCS"))

    assert _paths(store) == {"C:\\Docs2\\keep.txt"}


def test_delete_wraps_a_backend_failure_in_indexing_error(store: VectorStore, mocker: MockerFixture) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\a.txt")])
    store._writer.close()

    with pytest.raises(IndexingError):
        store.delete_by_path("C:\\Docs\\a.txt")


def test_ensure_compatible_is_false_for_a_fresh_store(store: VectorStore) -> None:
    assert store.ensure_compatible(MODEL) is False


def test_ensure_compatible_records_the_model_and_schema(store: VectorStore) -> None:
    store.ensure_compatible(MODEL)

    meta = dict(store._read("SELECT key, value FROM meta"))
    assert meta == {"schema_version": SCHEMA_VERSION, "embedding_model": MODEL}


def test_ensure_compatible_keeps_the_table_for_the_same_model(store: VectorStore) -> None:
    store.ensure_compatible(MODEL)
    store.upsert_chunks([_chunk("C:\\Docs\\a.txt")])

    assert store.ensure_compatible(MODEL) is False
    assert store.count() == 1


def test_ensure_compatible_drops_the_table_when_the_model_changes(store: VectorStore) -> None:
    store.ensure_compatible(MODEL)
    store.upsert_chunks([_chunk("C:\\Docs\\a.txt")])

    assert store.ensure_compatible("another/model") is True
    assert store.count() == 0


def test_ensure_compatible_drops_chunks_written_without_metadata(store: VectorStore) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\a.txt")])

    assert store.ensure_compatible(MODEL) is True
    assert store.count() == 0


def test_drop_all_lets_the_next_upsert_recreate_the_table(store: VectorStore) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\a.txt")])
    store.drop_all()

    store.upsert_chunks([_chunk("C:\\Docs\\b.txt")])

    assert _paths(store) == {"C:\\Docs\\b.txt"}


def test_optimize_keeps_every_row_searchable(store: VectorStore) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\a.txt", "Invoice INV-2231")])
    store.upsert_chunks([_chunk("C:\\Docs\\b.txt", "Invoice INV-9999")])

    store.optimize()

    assert store.search_text("INV-9999")[0].file_name == "b.txt"


def test_optimize_logs_rather_than_raises_on_failure(store: VectorStore, mocker: MockerFixture) -> None:
    store.upsert_chunks([_chunk("C:\\Docs\\a.txt")])
    store._writer.close()

    store.optimize()

    assert store.count() == 1


def test_reconnecting_picks_up_the_existing_table(tmp_path: Path) -> None:
    first = VectorStore(db_path=tmp_path / "search.db")
    first.connect()
    first.upsert_chunks([_chunk("C:\\Docs\\a.txt", content_hash="abc")])

    second = VectorStore(db_path=tmp_path / "search.db")
    second.connect()

    assert second.content_hash_for("C:\\Docs\\a.txt") == "abc"


def test_close_is_safe_to_call_twice(store: VectorStore) -> None:
    store.close()
    store.close()

    with pytest.raises(IndexingError):
        store.count()
