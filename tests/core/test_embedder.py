from __future__ import annotations

from unittest.mock import Mock

import numpy as np
import pytest
from pytest_mock import MockerFixture

import config.settings as settings_module
import core.embedder as embedder_module
from config.paths import model_cache_dir
from config.settings import Settings
from core.embedder import EMBED_BATCH_SIZE, Embedder, get_embedder
from core.exceptions import IndexingError


@pytest.fixture
def text_embedding(mocker: MockerFixture) -> Mock:
    """Replaces fastembed so no model is ever downloaded or loaded."""
    model_cls = mocker.patch("core.embedder.TextEmbedding")
    model = model_cls.return_value
    model.passage_embed.side_effect = lambda texts, batch_size: (np.array([float(len(t)), 0.5]) for t in texts)
    model.query_embed.side_effect = lambda query: iter([np.array([0.25, 0.75])])
    return model_cls


def test_embed_returns_an_empty_list_without_loading_the_model(text_embedding: Mock) -> None:
    assert Embedder("bge", threads=1).embed([]) == []
    text_embedding.assert_not_called()


def test_embed_returns_one_plain_float_list_per_text(text_embedding: Mock) -> None:
    vectors = Embedder("bge", threads=1).embed(["ab", "abcd"])

    assert vectors == [[2.0, 0.5], [4.0, 0.5]]
    assert all(type(v) is list for v in vectors)


def test_embed_uses_passage_embedding_in_batches(text_embedding: Mock) -> None:
    Embedder("bge", threads=1).embed(["ab"])

    assert text_embedding.return_value.passage_embed.call_args.kwargs == {"batch_size": EMBED_BATCH_SIZE}


def test_embed_wraps_a_model_failure_in_indexing_error(text_embedding: Mock) -> None:
    text_embedding.return_value.passage_embed.side_effect = RuntimeError("onnx crashed")

    with pytest.raises(IndexingError):
        Embedder("bge", threads=1).embed(["ab"])


def test_embed_query_uses_the_query_side_embedding(text_embedding: Mock) -> None:
    assert Embedder("bge", threads=1).embed_query("where is my invoice") == [0.25, 0.75]
    text_embedding.return_value.query_embed.assert_called_once_with("where is my invoice")


def test_embed_query_wraps_a_model_failure_in_indexing_error(text_embedding: Mock) -> None:
    text_embedding.return_value.query_embed.side_effect = RuntimeError("onnx crashed")

    with pytest.raises(IndexingError):
        Embedder("bge", threads=1).embed_query("anything")


def test_load_builds_the_model_with_the_cache_dir_and_thread_count(text_embedding: Mock) -> None:
    Embedder("BAAI/bge-small-en-v1.5", threads=3).load()

    text_embedding.assert_called_once_with("BAAI/bge-small-en-v1.5", cache_dir=str(model_cache_dir()), threads=3)


def test_load_only_builds_the_model_once(text_embedding: Mock) -> None:
    embedder = Embedder("bge", threads=1)

    embedder.load()
    embedder.embed(["a"])
    embedder.embed_query("b")

    text_embedding.assert_called_once()


def test_load_raises_indexing_error_when_the_model_cannot_load(text_embedding: Mock) -> None:
    text_embedding.side_effect = ValueError("model not found")

    with pytest.raises(IndexingError, match="not-a-model"):
        Embedder("not-a-model", threads=1).load()


def test_model_name_reports_the_configured_model() -> None:
    assert Embedder("bge", threads=1).model_name == "bge"


def test_get_embedder_builds_from_settings_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embedder_module, "_embedder", None)
    monkeypatch.setattr(settings_module, "_settings", Settings(_env_file=None, embedding_model="custom/model"))

    first = get_embedder()

    assert first is get_embedder()
    assert first.model_name == "custom/model"
