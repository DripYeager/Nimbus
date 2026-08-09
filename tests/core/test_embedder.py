from __future__ import annotations

import pytest

from core.embedder import Embedder, get_embedder
from core.exceptions import IndexingError


def test_embed_with_empty_list_returns_empty_list() -> None:
    assert Embedder("all-MiniLM-L6-v2").embed([]) == []


def test_embed_returns_one_vector_per_text_at_the_expected_dimension() -> None:
    vectors = Embedder("all-MiniLM-L6-v2").embed(["hello world", "a second chunk of text"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 384
    assert all(isinstance(v, float) for v in vectors[0])


def test_load_raises_indexing_error_for_an_unknown_model() -> None:
    with pytest.raises(IndexingError):
        Embedder("not-a-real-model-xyz").load()


def test_get_embedder_returns_the_same_instance_every_call() -> None:
    assert get_embedder() is get_embedder()
