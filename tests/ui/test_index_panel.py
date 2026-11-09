from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from models.schema import IndexStatus
from ui.api_client import ApiClient
from ui.settings.index_panel import IndexPanel, describe_index_status


def _synchronous(fn: Any, ok: Any, err: Any = None) -> None:
    ok(fn())


@pytest.fixture
def api(mocker: MockerFixture) -> Mock:
    fake = mocker.Mock(spec=ApiClient)
    fake.index_status.return_value = IndexStatus(content_files=5600, indexed_files=1240, failed_files=3)
    mocker.patch("ui.settings.index_panel.run_in_background", side_effect=_synchronous)
    return fake


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (
            IndexStatus(content_files=5600, indexed_files=1240, failed_files=3),
            "Indexed 1,240 of 5,600 files · 3 failed",
        ),
        (IndexStatus(content_files=10, indexed_files=10), "Indexed 10 of 10 files"),
        (IndexStatus(is_paused=True, is_scanning=True), "Paused"),
        (IndexStatus(is_scanning=True), "Scanning…"),
    ],
)
def test_describe_index_status_formats_progress(status: IndexStatus, expected: str) -> None:
    assert describe_index_status(status) == expected


def test_index_panel_refresh_shows_status(api: Mock) -> None:
    panel = IndexPanel(api)
    panel.refresh()
    assert panel._status.text() == "Indexed 1,240 of 5,600 files · 3 failed"


def test_index_panel_toggle_pause_pauses_and_offers_resume(api: Mock) -> None:
    api.set_paused.return_value = IndexStatus(is_paused=True)
    panel = IndexPanel(api)
    panel._toggle_pause()
    api.set_paused.assert_called_once_with(True)
    assert panel._pause_button.text() == "Resume"


def test_index_panel_confirm_rebuild_skips_when_declined(api: Mock, mocker: MockerFixture) -> None:
    mocker.patch("ui.settings.index_panel.QMessageBox.question", return_value=mocker.Mock())
    IndexPanel(api)._confirm_rebuild()
    api.rebuild_index.assert_not_called()


def test_index_panel_shows_error_when_engine_unreachable(mocker: MockerFixture) -> None:
    mocker.patch("ui.settings.index_panel.run_in_background", side_effect=lambda fn, ok, err=None: err("No engine"))
    panel = IndexPanel(mocker.Mock(spec=ApiClient))
    panel.refresh()
    assert panel._status.text() == "No engine"
    assert panel._status.property("role") == "error"
