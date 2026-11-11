from __future__ import annotations

from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from core.desktop_control import AppWindow
from core.exceptions import ToolError
from tools.desktop_tools import DesktopToolbox
from tools.registry import ToolRegistry

EXCEL = AppWindow(1, "Budget.xlsx - Excel", "EXCEL")


@pytest.fixture
def control(mocker: MockerFixture) -> Mock:
    fake = mocker.patch("tools.desktop_tools.desktop_control")
    fake.find_window.return_value = EXCEL
    fake.open_windows.return_value = [EXCEL]
    fake.set_volume.return_value = 40
    return fake


def test_copy_puts_the_text_on_the_clipboard(control: Mock) -> None:
    result = DesktopToolbox().copy({"text": "| a | b |"})

    control.copy_text.assert_called_once_with("| a | b |")
    assert "Copied 9 characters" in result.content


def test_copy_refuses_empty_text(control: Mock) -> None:
    with pytest.raises(ToolError):
        DesktopToolbox().copy({"text": "  "})


def test_media_volume_defaults_to_a_few_steps(control: Mock) -> None:
    DesktopToolbox().media({"action": "volume_up"})

    control.press_media_key.assert_called_once_with("volume_up", 5)


def test_media_play_pause_presses_once(control: Mock) -> None:
    DesktopToolbox().media({"action": "Play_Pause"})

    control.press_media_key.assert_called_once_with("play_pause", 1)


def test_volume_reports_what_it_set(control: Mock) -> None:
    assert DesktopToolbox().volume({"percent": 41}).content == "Volume set to about 40%."


def test_switch_and_close_act_on_the_matching_window(control: Mock) -> None:
    DesktopToolbox().switch({"name": "excel"})
    DesktopToolbox().close({"name": "excel"})

    control.switch_to.assert_called_once_with(EXCEL)
    control.close.assert_called_once_with(EXCEL)


def test_list_windows_shows_program_and_title(control: Mock) -> None:
    assert DesktopToolbox().list_windows({}).content == "- EXCEL: Budget.xlsx - Excel"


def test_only_closing_asks_first() -> None:
    registry = ToolRegistry()
    DesktopToolbox().register(registry)

    asking = [name for name in registry.names() if registry.get(name).needs_confirmation({})]  # type: ignore[union-attr]

    assert asking == ["close_window"]
