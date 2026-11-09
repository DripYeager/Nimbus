from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

import config.settings as settings_module
from config.settings import Settings
from core.embedder import Embedder
from core.exceptions import IndexingError, ParsingError
from core.indexer import Indexer, hash_file
from core.vector_store import VectorStore


@pytest.fixture
def store(mocker: MockerFixture) -> Mock:
    fake = mocker.Mock(spec=VectorStore)
    fake.content_hash_for.return_value = None
    return fake


@pytest.fixture
def embedder(mocker: MockerFixture) -> Mock:
    fake = mocker.Mock(spec=Embedder)
    fake.embed.side_effect = lambda texts: [[0.1, 0.2, 0.3] for _ in texts]
    return fake


@pytest.fixture
def parsed_text(mocker: MockerFixture) -> Mock:
    """Stands in for the parser so these tests exercise the pipeline, not file formats."""
    return mocker.patch("core.indexer.extract_document_text", return_value="one two three four five")


@pytest.fixture
def note(tmp_path: Path) -> Path:
    path = tmp_path / "Note.TXT"
    path.write_text("one two three four five", encoding="utf-8")
    return path


def test_index_file_embeds_and_stores_a_new_files_chunks(
    note: Path, store: Mock, embedder: Mock, parsed_text: Mock
) -> None:
    written = Indexer(store, embedder).index_file(note)

    [chunks] = store.upsert_chunks.call_args.args
    assert written == 1
    assert [c.chunk_text for c in chunks] == ["one two three four five"]


def test_index_file_tags_each_chunk_with_its_file_and_content_hash(
    note: Path, store: Mock, embedder: Mock, parsed_text: Mock
) -> None:
    Indexer(store, embedder).index_file(note)

    [chunk] = store.upsert_chunks.call_args.args[0]
    assert (chunk.file_path, chunk.file_name, chunk.file_type) == (str(note), "Note.TXT", "txt")
    assert chunk.content_hash == hash_file(note)


def test_index_file_chunks_with_the_configured_sizes(
    note: Path, store: Mock, embedder: Mock, parsed_text: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings_module, "_settings", Settings(_env_file=None, max_chunk_size=2, chunk_overlap=0))

    assert Indexer(store, embedder).index_file(note) == 3


def test_index_file_skips_re_embedding_when_the_content_hash_is_unchanged(
    note: Path, store: Mock, embedder: Mock, parsed_text: Mock
) -> None:
    store.content_hash_for.return_value = hash_file(note)

    assert Indexer(store, embedder).index_file(note) == 0
    parsed_text.assert_not_called()
    embedder.embed.assert_not_called()


def test_index_file_reindexes_when_the_content_hash_changed(
    note: Path, store: Mock, embedder: Mock, parsed_text: Mock
) -> None:
    store.content_hash_for.return_value = "hash-of-an-older-version"

    Indexer(store, embedder).index_file(note)

    store.upsert_chunks.assert_called_once()


def test_index_file_clears_old_rows_when_no_text_is_extracted(
    note: Path, store: Mock, embedder: Mock, parsed_text: Mock
) -> None:
    parsed_text.return_value = "   "

    assert Indexer(store, embedder).index_file(note) == 0
    store.delete_by_path.assert_called_once_with(str(note))
    store.upsert_chunks.assert_not_called()


def test_index_file_raises_indexing_error_for_a_missing_file(tmp_path: Path, store: Mock, embedder: Mock) -> None:
    with pytest.raises(IndexingError):
        Indexer(store, embedder).index_file(tmp_path / "gone.txt")


def test_index_file_lets_a_parsing_error_propagate(note: Path, store: Mock, embedder: Mock, parsed_text: Mock) -> None:
    parsed_text.side_effect = ParsingError("encrypted")

    with pytest.raises(ParsingError):
        Indexer(store, embedder).index_file(note)


def test_index_file_writes_nothing_when_embedding_fails(
    note: Path, store: Mock, embedder: Mock, parsed_text: Mock
) -> None:
    embedder.embed.side_effect = IndexingError("model crashed")

    with pytest.raises(IndexingError):
        Indexer(store, embedder).index_file(note)
    store.upsert_chunks.assert_not_called()


def test_optimize_store_delegates_to_the_store(store: Mock, embedder: Mock) -> None:
    Indexer(store, embedder).optimize_store()

    store.optimize.assert_called_once()


def test_hash_file_streams_a_file_larger_than_one_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("core.indexer.HASH_BLOCK_BYTES", 4)
    content = b"0123456789abcdef-tail"
    path = tmp_path / "big.bin"
    path.write_bytes(content)

    assert hash_file(path) == hashlib.md5(content).hexdigest()


def test_hash_file_raises_indexing_error_for_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(IndexingError):
        hash_file(tmp_path / "gone.bin")
