from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from core.exceptions import AppLaunchError
from models.schema import AppEntry
from tools.app_launcher import launch_app


def test_launch_app_opens_start_menu_shortcut(mocker: MockerFixture) -> None:
    startfile = mocker.patch("tools.app_launcher.os.startfile", create=True)
    launch_app(AppEntry(name="Word", launch_target="C:/Start/Word.lnk", source="start_menu"))
    startfile.assert_called_once_with("C:/Start/Word.lnk")


def test_launch_app_opens_registry_executable(mocker: MockerFixture) -> None:
    startfile = mocker.patch("tools.app_launcher.os.startfile", create=True)
    launch_app(AppEntry(name="chrome", launch_target="C:/Chrome/chrome.exe", source="registry"))
    startfile.assert_called_once_with("C:/Chrome/chrome.exe")


def test_launch_app_activates_store_app_through_apps_folder(mocker: MockerFixture) -> None:
    popen = mocker.patch("tools.app_launcher.subprocess.Popen")
    launch_app(AppEntry(name="Calculator", launch_target="Microsoft.WindowsCalculator!App", source="store_app"))
    popen.assert_called_once_with(["explorer.exe", "shell:AppsFolder\\Microsoft.WindowsCalculator!App"])


def test_launch_app_raises_when_shortcut_is_gone(mocker: MockerFixture) -> None:
    mocker.patch("tools.app_launcher.os.startfile", create=True, side_effect=FileNotFoundError("missing"))
    with pytest.raises(AppLaunchError, match="refresh the app catalog"):
        launch_app(AppEntry(name="Word", launch_target="C:/Start/Word.lnk", source="start_menu"))


def test_launch_app_raises_when_explorer_cannot_start(mocker: MockerFixture) -> None:
    mocker.patch("tools.app_launcher.subprocess.Popen", side_effect=OSError("no explorer"))
    with pytest.raises(AppLaunchError, match="Calculator"):
        launch_app(AppEntry(name="Calculator", launch_target="Calc!App", source="store_app"))
