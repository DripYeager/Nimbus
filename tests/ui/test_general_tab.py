from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from core.exceptions import AutostartError
from models.api import UsageView
from ui.api_client import ApiClient
from ui.settings.general_tab import GeneralTab, describe_usage

VALUES: dict[str, Any] = {
    "hotkey": "<ctrl>+<shift>+n",
    "daily_llm_call_cap": 200,
    "auto_approved_tools": ["open_app", "save_note"],
}


@pytest.fixture
def api(mocker: MockerFixture) -> Mock:
    mocker.patch("ui.settings.general_tab.run_in_background", side_effect=lambda fn, ok, err=None: ok(fn()))
    mocker.patch("ui.settings.general_tab.is_autostart_enabled", return_value=False)
    fake = mocker.Mock(spec=ApiClient)
    fake.usage.return_value = UsageView(calls_today=12, daily_cap=200)
    return fake


def test_collect_round_trips_loaded_values(api: Mock) -> None:
    tab = GeneralTab(api)
    tab.load(VALUES)
    assert tab.collect() == VALUES


def test_collect_maps_zero_cap_to_none(api: Mock) -> None:
    tab = GeneralTab(api)
    tab.load({**VALUES, "daily_llm_call_cap": None})
    assert tab.collect()["daily_llm_call_cap"] is None


def test_collect_omits_unusable_hotkey(api: Mock) -> None:
    tab = GeneralTab(api)
    tab.load({**VALUES, "hotkey": "nonsense"})
    assert "hotkey" not in tab.collect()


def test_load_shows_usage(api: Mock) -> None:
    tab = GeneralTab(api)
    tab.load(VALUES)
    assert tab._usage_label.text() == "12 model calls today"


def test_describe_usage_uses_singular_for_one_call() -> None:
    assert describe_usage(UsageView(calls_today=1, daily_cap=None)) == "1 model call today"


def test_autostart_toggle_enables_immediately(api: Mock, mocker: MockerFixture) -> None:
    enable = mocker.patch("ui.settings.general_tab.enable_autostart")
    tab = GeneralTab(api)
    tab.load(VALUES)
    tab._autostart_box.setChecked(True)
    enable.assert_called_once()


def test_autostart_toggle_reverts_and_explains_on_failure(api: Mock, mocker: MockerFixture) -> None:
    mocker.patch("ui.settings.general_tab.enable_autostart", side_effect=AutostartError("Startup folder is locked"))
    tab = GeneralTab(api)
    tab.load(VALUES)
    tab._autostart_box.setChecked(True)
    assert not tab._autostart_box.isChecked()
    assert tab._autostart_error.text() == "Startup folder is locked"
    assert not tab._autostart_error.isHidden()


def test_load_does_not_touch_autostart(api: Mock, mocker: MockerFixture) -> None:
    mocker.patch("ui.settings.general_tab.is_autostart_enabled", return_value=True)
    enable = mocker.patch("ui.settings.general_tab.enable_autostart")
    tab = GeneralTab(api)
    tab.load(VALUES)
    assert tab._autostart_box.isChecked()
    enable.assert_not_called()
