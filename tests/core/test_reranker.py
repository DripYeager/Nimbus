from __future__ import annotations

from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

import core.reranker as reranker_module
from core.reranker import Reranker, blend, get_reranker
from models.schema import SearchResult


def _result(chunk_id: str) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        chunk_text=f"text {chunk_id}",
        file_path=f"C:/{chunk_id}.txt",
        file_name=f"{chunk_id}.txt",
        score=0.0,
        metadata={},
    )


@pytest.fixture
def model(mocker: MockerFixture) -> Mock:
    fake = mocker.Mock()
    return mocker.patch("core.reranker.TextCrossEncoder", return_value=fake).return_value


def test_rerank_keeps_the_first_pass_order_until_the_model_is_ready() -> None:
    candidates = [_result("a"), _result("b"), _result("c")]

    assert Reranker("m", 1).rerank("q", candidates, 2) == candidates[:2]


def test_rerank_moves_up_what_the_model_rates_highest(model: Mock) -> None:
    model.rerank.return_value = [0.1, 0.2, 9.0]
    reranker = Reranker("m", 1)
    reranker.load()

    ranked = reranker.rerank("q", [_result("a"), _result("b"), _result("c")], 3)

    # Blended with the first pass, the model's clear favourite still rises above the middle.
    assert [r.chunk_id for r in ranked].index("c") < 2


def test_rerank_falls_back_when_the_model_fails(model: Mock) -> None:
    model.rerank.side_effect = RuntimeError("onnx error")
    reranker = Reranker("m", 1)
    reranker.load()
    candidates = [_result("a"), _result("b")]

    assert reranker.rerank("q", candidates, 2) == candidates


def test_load_remembers_a_failure_and_stays_off(mocker: MockerFixture) -> None:
    loader = mocker.patch("core.reranker.TextCrossEncoder", side_effect=OSError("offline"))
    reranker = Reranker("m", 1)

    reranker.load()
    reranker.load()

    assert (reranker.is_ready(), loader.call_count) == (False, 1)


def test_blend_keeps_a_result_both_orders_agree_on_at_the_top() -> None:
    a, b, c = _result("a"), _result("b"), _result("c")

    assert blend([a, b, c], [a, c, b])[0].chunk_id == "a"


def test_get_reranker_is_none_when_switched_off(mocker: MockerFixture) -> None:
    mocker.patch("core.reranker.get_settings", return_value=mocker.Mock(rerank_enabled=False))

    assert get_reranker() is None


def test_get_reranker_builds_one_shared_instance(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reranker_module, "_reranker", None)
    mocker.patch(
        "core.reranker.get_settings",
        return_value=mocker.Mock(rerank_enabled=True, rerank_model="m", embedding_threads=1),
    )

    assert get_reranker() is get_reranker()
