from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from models.api import OllamaStatus
from ui.api_client import ApiClient
from ui.settings.ollama_helper import DOWNLOAD_PAGE, OllamaHelper, describe_ollama

MODEL = "qwen2.5:7b"


def _run_now(fn: Any, ok: Any, err: Any = None) -> None:
    ok(fn())


@pytest.fixture
def api(mocker: MockerFixture) -> Mock:
    return mocker.Mock(spec=ApiClient)


@pytest.fixture
def helper(mocker: MockerFixture, api: Mock) -> OllamaHelper:
    mocker.patch("ui.settings.ollama_helper.run_in_background", side_effect=_run_now)
    return OllamaHelper(api)


def _status(**fields: Any) -> OllamaStatus:
    return OllamaStatus(**{"installed": True, "running": True, **fields})


def test_describe_ollama_offers_the_download_page_when_not_installed() -> None:
    assert describe_ollama(_status(installed=False, running=False), MODEL)[2] == "Get Ollama"


def test_describe_ollama_offers_to_start_an_installed_server() -> None:
    assert describe_ollama(_status(running=False), MODEL)[2] == "Start Ollama"


def test_describe_ollama_offers_to_download_a_missing_model() -> None:
    assert describe_ollama(_status(), MODEL)[2] == f"Download {MODEL}"


def test_describe_ollama_shows_download_progress() -> None:
    headline, _, button = describe_ollama(_status(pulling=MODEL, pull_percent=42.4), MODEL)
    assert (headline, button) == (f"Downloading {MODEL} · 42%", None)


def test_describe_ollama_is_ready_once_the_model_is_there() -> None:
    assert describe_ollama(_status(has_model=True), MODEL)[0] == "Ready"


def test_describe_ollama_offers_a_retry_after_a_failed_download() -> None:
    assert describe_ollama(_status(pull_error="network down"), MODEL)[2] == f"Retry {MODEL}"


def test_watch_checks_the_model_right_away(helper: OllamaHelper, api: Mock) -> None:
    api.ollama_status.return_value = _status(has_model=True)

    helper.watch(MODEL)

    api.ollama_status.assert_called_once_with(MODEL)
    assert helper._headline.text() == "Ready"


def test_button_opens_the_download_page_when_not_installed(
    helper: OllamaHelper, api: Mock, mocker: MockerFixture
) -> None:
    opened = mocker.patch("ui.settings.ollama_helper.QDesktopServices.openUrl")
    api.ollama_status.return_value = _status(installed=False, running=False)
    helper.watch(MODEL)

    helper._action.click()

    assert opened.call_args.args[0].toString() == DOWNLOAD_PAGE


def test_button_starts_ollama_when_installed(helper: OllamaHelper, api: Mock) -> None:
    api.ollama_status.return_value = _status(running=False)
    api.start_ollama.return_value = _status()
    helper.watch(MODEL)

    helper._action.click()

    api.start_ollama.assert_called_once()


def test_button_downloads_the_watched_model(helper: OllamaHelper, api: Mock) -> None:
    api.ollama_status.return_value = _status()
    api.pull_ollama_model.return_value = _status(pulling=MODEL, pull_percent=0.0)
    helper.watch(MODEL)

    helper._action.click()

    api.pull_ollama_model.assert_called_once_with(MODEL)
    assert not helper._progress.isHidden()


def test_check_failure_explains_the_problem(mocker: MockerFixture, api: Mock) -> None:
    mocker.patch(
        "ui.settings.ollama_helper.run_in_background",
        side_effect=lambda fn, ok, err=None: err("Couldn't reach Nimbus's engine."),
    )
    helper = OllamaHelper(api)

    helper.watch(MODEL)

    assert (helper._headline.text(), helper._detail.text()) == (
        "Couldn't check Ollama",
        "Couldn't reach Nimbus's engine.",
    )
