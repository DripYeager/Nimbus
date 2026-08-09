from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from core.embedder import Embedder
from core.exceptions import IndexingError, ParsingError, UnsupportedFileTypeError
from core.indexer import Indexer
from core.vector_store import VectorStore
from models.schema import IndexedChunk, ParsedDocument


@pytest.fixture
def store(mocker: MockerFixture) -> VectorStore:
    fake = mocker.Mock(spec=VectorStore)
    fake.get_by_hash.return_value = None
    return fake


@pytest.fixture
def embedder(mocker: MockerFixture) -> Embedder:
    fake = mocker.Mock(spec=Embedder)
    fake.embed.side_effect = lambda texts: [[0.1, 0.2, 0.3] for _ in texts]
    return fake


def test_index_file_skips_a_file_whose_hash_is_already_indexed(
    tmp_path: Path, store: VectorStore, embedder: Embedder
) -> None:
    now = datetime.now()
    store.get_by_hash.return_value = IndexedChunk(
        id="x",
        file_path="a",
        file_name="a",
        file_type="txt",
        content_hash="h",
        chunk_index=0,
        chunk_text="t",
        vector=[0.1],
        created_at=now,
        modified_at=now,
        indexed_at=now,
    )
    path = tmp_path / "a.txt"
    path.write_text("some content")

    assert Indexer(store, embedder).index_file(path) == 0
    embedder.embed.assert_not_called()
    store.upsert_chunks.assert_not_called()


def test_index_file_embeds_and_stores_a_new_files_chunks(
    tmp_path: Path, store: VectorStore, embedder: Embedder, mocker: MockerFixture
) -> None:
    mocker.patch(
        "core.document_parser.parse_document",
        return_value=ParsedDocument(markdown_text="one two three four five", needs_ocr=False),
    )
    path = tmp_path / "a.txt"
    path.write_text("one two three four five")

    written = Indexer(store, embedder).index_file(path)

    assert written == 1
    store.upsert_chunks.assert_called_once()
    chunks = store.upsert_chunks.call_args[0][0]
    assert len(chunks) == 1
    assert chunks[0].chunk_text == "one two three four five"
    assert chunks[0].file_name == "a.txt"


def test_index_file_falls_back_to_ocr_for_a_thin_pdf(
    tmp_path: Path, store: VectorStore, embedder: Embedder, mocker: MockerFixture
) -> None:
    mocker.patch("core.document_parser.parse_document", return_value=ParsedDocument(markdown_text="", needs_ocr=True))
    ocr_spy = mocker.patch("core.document_parser.extract_text_with_ocr", return_value="recovered scanned text here")
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-1.4 fake")

    written = Indexer(store, embedder).index_file(path)

    ocr_spy.assert_called_once_with(path)
    assert written == 1


def test_index_file_does_not_ocr_a_thin_non_pdf(
    tmp_path: Path, store: VectorStore, embedder: Embedder, mocker: MockerFixture
) -> None:
    mocker.patch("core.document_parser.parse_document", return_value=ParsedDocument(markdown_text="", needs_ocr=True))
    ocr_spy = mocker.patch("core.document_parser.extract_text_with_ocr")
    path = tmp_path / "empty.txt"
    path.write_text("")

    written = Indexer(store, embedder).index_file(path)

    ocr_spy.assert_not_called()
    assert written == 0


def test_index_file_returns_zero_when_no_text_is_extracted(
    tmp_path: Path, store: VectorStore, embedder: Embedder, mocker: MockerFixture
) -> None:
    mocker.patch("core.document_parser.parse_document", return_value=ParsedDocument(markdown_text="   ", needs_ocr=False))
    path = tmp_path / "blank.txt"
    path.write_text(" ")

    assert Indexer(store, embedder).index_file(path) == 0
    store.upsert_chunks.assert_not_called()


def test_index_file_raises_indexing_error_for_a_missing_file(store: VectorStore, embedder: Embedder) -> None:
    with pytest.raises(IndexingError):
        Indexer(store, embedder).index_file(Path("does-not-exist.txt"))


def test_index_directory_sums_chunks_across_files(
    tmp_path: Path, store: VectorStore, embedder: Embedder, mocker: MockerFixture
) -> None:
    mocker.patch(
        "core.document_parser.parse_document",
        side_effect=lambda path: ParsedDocument(markdown_text=f"text for {path.name} words here", needs_ocr=False),
    )
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")

    total = Indexer(store, embedder).index_directory(tmp_path)

    assert total == 2
    assert store.upsert_chunks.call_count == 2


def test_index_directory_logs_an_unsupported_file_type_at_info_not_error(
    tmp_path: Path,
    store: VectorStore,
    embedder: Embedder,
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    mocker.patch(
        "core.document_parser.parse_document",
        side_effect=UnsupportedFileTypeError("no converter for .blend"),
    )
    (tmp_path / "model.blend").write_bytes(b"fake binary content")

    with caplog.at_level(logging.INFO):
        total = Indexer(store, embedder).index_directory(tmp_path)

    assert total == 0
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)
    blend_path = str(tmp_path / "model.blend")
    assert any(
        record.levelno == logging.INFO and getattr(record, "path", None) == blend_path for record in caplog.records
    )


def test_index_directory_skips_a_file_that_fails_and_keeps_going(
    tmp_path: Path, store: VectorStore, embedder: Embedder, mocker: MockerFixture
) -> None:
    def fake_parse(path: Path) -> ParsedDocument:
        if path.name == "broken.txt":
            raise ParsingError("simulated failure")
        return ParsedDocument(markdown_text="fine words here", needs_ocr=False)

    mocker.patch("core.document_parser.parse_document", side_effect=fake_parse)
    (tmp_path / "broken.txt").write_text("x")
    (tmp_path / "fine.txt").write_text("y")

    total = Indexer(store, embedder).index_directory(tmp_path)

    assert total == 1
    assert store.upsert_chunks.call_count == 1


def test_index_file_and_index_directory_work_end_to_end_with_real_dependencies(tmp_path: Path) -> None:
    from core.embedder import get_embedder

    (tmp_path / "notes.txt").write_text("Nimbus indexes real files end to end during this test.")
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()

    real_store = VectorStore(db_path=tmp_path / "index")
    real_store.connect()
    total = Indexer(real_store, get_embedder()).index_directory(empty_dir)
    assert total == 0

    total = Indexer(real_store, get_embedder()).index_file(tmp_path / "notes.txt")
    assert total == 1
    assert real_store.count() == 1
