from __future__ import annotations

from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from core import desktop_control
from core.desktop_control import AppWindow, find_window, press_media_key, set_volume
from core.exceptions import ToolError

WINDOWS = [
    AppWindow(1, "Budget 2026.xlsx - Excel", "EXCEL"),
    AppWindow(2, "Spotify Premium", "Spotify"),
    AppWindow(3, "Inbox - Google Chrome", "chrome"),
]


@pytest.fixture
def keys(mocker: MockerFixture) -> Mock:
    mocker.patch("core.desktop_control.time.sleep")
    return mocker.patch("core.desktop_control.win32api.keybd_event")


@pytest.fixture
def windows(mocker: MockerFixture) -> None:
    mocker.patch("core.desktop_control.open_windows", return_value=WINDOWS)


def test_press_media_key_presses_and_releases_once(keys: Mock) -> None:
    press_media_key("play_pause")

    assert [c.args[0] for c in keys.call_args_list] == [0xB3, 0xB3]


def test_press_media_key_rejects_an_unknown_action(keys: Mock) -> None:
    with pytest.raises(ToolError, match="Unknown media action"):
        press_media_key("rewind")


def test_set_volume_goes_to_zero_then_steps_up(keys: Mock) -> None:
    assert set_volume(30) == 30
    presses = [c.args[0] for c in keys.call_args_list if c.args[2] == 0]
    assert presses.count(0xAE) == 50 and presses.count(0xAF) == 15


def test_set_volume_clamps_to_the_valid_range(keys: Mock) -> None:
    assert set_volume(140) == 100


@pytest.mark.parametrize(("query", "handle"), [("excel", 1), ("Spotify.exe", 2), ("inbox", 3), ("budget", 1)])
def test_find_window_matches_program_then_title(windows: None, query: str, handle: int) -> None:
    assert find_window(query).handle == handle


def test_find_window_names_the_open_programs_when_nothing_matches(windows: None) -> None:
    with pytest.raises(ToolError, match="Open programs: EXCEL, Spotify, chrome"):
        find_window("photoshop")


def test_was_copied_by_nimbus_recognises_its_own_text(mocker: MockerFixture) -> None:
    mocker.patch.object(desktop_control, "_last_copied", "the answer")

    assert desktop_control.was_copied_by_nimbus(" the answer ") and not desktop_control.was_copied_by_nimbus("other")
