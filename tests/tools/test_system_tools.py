from __future__ import annotations

from collections import namedtuple
from pathlib import Path
from unittest.mock import MagicMock

import psutil
import pytest
from pytest_mock import MockerFixture

from core.exceptions import ToolError
from tools.system_tools import (
    SETTINGS_PAGES,
    open_path,
    open_url,
    open_windows_setting,
    read_system_status,
    reveal_in_explorer,
)

Battery = namedtuple("Battery", "percent secsleft power_plugged")
DiskUsage = namedtuple("DiskUsage", "total used free percent")
Memory = namedtuple("Memory", "percent")
GB = 1024**3


@pytest.fixture
def startfile(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("tools.system_tools.os.startfile", create=True)


@pytest.fixture
def machine(mocker: MockerFixture) -> MagicMock:
    fake = mocker.patch("tools.system_tools.psutil")
    fake.Error = psutil.Error
    fake.sensors_battery.return_value = Battery(percent=76, secsleft=3600, power_plugged=False)
    fake.disk_usage.return_value = DiskUsage(total=500 * GB, used=380 * GB, free=120 * GB, percent=76.0)
    fake.cpu_percent.return_value = 12.5
    fake.virtual_memory.return_value = Memory(percent=48.0)
    mocker.patch("tools.system_tools.time.time", return_value=10_000.0)
    fake.boot_time.return_value = 10_000.0 - 5 * 3600
    return fake


def test_open_path_opens_existing_file(tmp_path: Path, startfile: MagicMock) -> None:
    report = tmp_path / "report.pdf"
    report.touch()
    open_path(report)
    startfile.assert_called_once_with(report)


def test_open_path_raises_for_missing_file(tmp_path: Path, startfile: MagicMock) -> None:
    with pytest.raises(ToolError, match="Nothing exists"):
        open_path(tmp_path / "missing.pdf")
    startfile.assert_not_called()


def test_open_path_raises_when_no_app_is_associated(tmp_path: Path, startfile: MagicMock) -> None:
    odd = tmp_path / "file.xyz"
    odd.touch()
    startfile.side_effect = OSError("No application is associated")
    with pytest.raises(ToolError, match="associated"):
        open_path(odd)


def test_reveal_in_explorer_selects_the_file(tmp_path: Path, mocker: MockerFixture) -> None:
    popen = mocker.patch("tools.system_tools.subprocess.Popen")
    target = tmp_path / "my report.docx"
    target.touch()
    reveal_in_explorer(target)
    popen.assert_called_once_with(f'explorer.exe /select,"{target}"')


def test_reveal_in_explorer_raises_for_missing_path(tmp_path: Path, mocker: MockerFixture) -> None:
    popen = mocker.patch("tools.system_tools.subprocess.Popen")
    with pytest.raises(ToolError):
        reveal_in_explorer(tmp_path / "missing.docx")
    popen.assert_not_called()


def test_open_url_opens_https_link(mocker: MockerFixture) -> None:
    browser = mocker.patch("tools.system_tools.webbrowser.open", return_value=True)
    open_url("https://example.com/page")
    browser.assert_called_once_with("https://example.com/page")


@pytest.mark.parametrize(
    "url", ["file:///C:/Windows/System32", "javascript:alert(1)", "ms-settings:display", "https://"]
)
def test_open_url_rejects_non_web_links(url: str, mocker: MockerFixture) -> None:
    browser = mocker.patch("tools.system_tools.webbrowser.open")
    with pytest.raises(ToolError, match="only http"):
        open_url(url)
    browser.assert_not_called()


def test_open_url_raises_when_no_browser_starts(mocker: MockerFixture) -> None:
    mocker.patch("tools.system_tools.webbrowser.open", return_value=False)
    with pytest.raises(ToolError, match="browser"):
        open_url("http://example.com")


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        ("Wi-Fi", "wifi"),
        ("Bluetooth settings", "bluetooth"),
        ("windows update", "windows-update"),
        ("Do Not Disturb", "do-not-disturb"),
        ("default_apps", "default-apps"),
        ("bluetoth", "bluetooth"),
    ],
)
def test_open_windows_setting_matches_loose_names(page: str, expected: str, startfile: MagicMock) -> None:
    assert open_windows_setting(page) == expected
    startfile.assert_called_once_with(SETTINGS_PAGES[expected])


def test_open_windows_setting_raises_with_valid_names(startfile: MagicMock) -> None:
    with pytest.raises(ToolError, match="Valid pages: .*bluetooth"):
        open_windows_setting("registry editor")
    startfile.assert_not_called()


def test_open_windows_setting_raises_for_blank_page(startfile: MagicMock) -> None:
    with pytest.raises(ToolError):
        open_windows_setting("  settings ")


def test_read_system_status_reports_battery_and_disk(machine: MagicMock) -> None:
    status = read_system_status()
    assert (status.battery_percent, status.is_plugged_in) == (76, False)
    assert (status.disk_free_gb, status.disk_total_gb) == (120.0, 500.0)
    assert (status.cpu_percent, status.memory_percent, status.uptime_hours) == (12.5, 48.0, 5.0)
    machine.disk_usage.assert_called_once_with(Path.home().anchor)


def test_read_system_status_without_battery(machine: MagicMock) -> None:
    machine.sensors_battery.return_value = None
    status = read_system_status()
    assert status.battery_percent is None
    assert status.is_plugged_in is None


def test_read_system_status_raises_when_counters_fail(machine: MagicMock) -> None:
    machine.disk_usage.side_effect = PermissionError("denied")
    with pytest.raises(ToolError, match="system status"):
        read_system_status()
