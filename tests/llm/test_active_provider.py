from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from config.settings import get_settings
from core.exceptions import ProviderError, UsageCapReachedError
from core.usage_meter import UsageMeter
from llm.active_provider import ActiveProvider
from llm.provider import LLMProvider
from models.chat import ChatMessage, TextDelta


@pytest.fixture
def meter(tmp_path: Path) -> UsageMeter:
    return UsageMeter(tmp_path / "usage.json")


@pytest.fixture
def backend(mocker: MockerFixture) -> Mock:
    backend = mocker.Mock(spec=LLMProvider)
    backend.complete.return_value = "answer"
    backend.stream_chat.return_value = iter([TextDelta(text="hi")])
    backend.list_models.return_value = ["m1"]
    return backend


@pytest.fixture
def get_provider(mocker: MockerFixture, backend: Mock) -> Mock:
    return mocker.patch("llm.active_provider.get_provider", return_value=backend)


def test_stream_chat_forwards_to_the_backend(get_provider: Mock, backend: Mock, meter: UsageMeter) -> None:
    messages = [ChatMessage(role="user", content="hi")]

    items = list(ActiveProvider(meter).stream_chat("system", messages, []))

    assert items == [TextDelta(text="hi")]
    backend.stream_chat.assert_called_once_with("system", messages, [])


def test_complete_counts_one_call_against_today(get_provider: Mock, meter: UsageMeter) -> None:
    ActiveProvider(meter).complete("prompt")

    assert meter.calls_today() == 1


def test_complete_raises_once_the_daily_cap_is_used_up(get_provider: Mock, backend: Mock, meter: UsageMeter) -> None:
    get_settings().daily_llm_call_cap = 1
    meter.record_call()

    with pytest.raises(UsageCapReachedError, match="limit of 1"):
        ActiveProvider(meter).complete("prompt")

    backend.complete.assert_not_called()


def test_stream_raises_once_the_daily_cap_is_used_up(get_provider: Mock, backend: Mock, meter: UsageMeter) -> None:
    get_settings().daily_llm_call_cap = 0

    with pytest.raises(UsageCapReachedError):
        ActiveProvider(meter).stream("prompt")

    backend.stream.assert_not_called()


def test_list_models_is_not_counted(get_provider: Mock, meter: UsageMeter) -> None:
    get_settings().daily_llm_call_cap = 0

    assert ActiveProvider(meter).list_models() == ["m1"]
    assert meter.calls_today() == 0


def test_is_available_forwards_to_the_backend(get_provider: Mock, backend: Mock, meter: UsageMeter) -> None:
    backend.is_available.return_value = False

    assert ActiveProvider(meter).is_available() is False


def test_backend_is_built_once_and_reused(get_provider: Mock, meter: UsageMeter) -> None:
    provider = ActiveProvider(meter)

    provider.complete("a")
    provider.complete("b")

    get_provider.assert_called_once()


def test_reload_swaps_the_backend(mocker: MockerFixture, meter: UsageMeter) -> None:
    old, new = mocker.Mock(spec=LLMProvider), mocker.Mock(spec=LLMProvider)
    new.complete.return_value = "from new"
    mocker.patch("llm.active_provider.get_provider", side_effect=[old, new])
    provider = ActiveProvider(meter)
    provider.complete("warm up")

    provider.reload()

    assert provider.complete("again") == "from new"


def test_reload_propagates_a_backend_that_cannot_be_built(mocker: MockerFixture, meter: UsageMeter) -> None:
    mocker.patch("llm.active_provider.get_provider", side_effect=ProviderError("needs a base URL"))

    with pytest.raises(ProviderError):
        ActiveProvider(meter).reload()
