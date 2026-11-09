from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture
from pywintypes import com_error

from core import autostart
from core.exceptions import AutostartError


@pytest.fixture
def startup_dir(tmp_path: Path, mocker: MockerFixture) -> Path:
    mocker.patch("core.autostart._startup_dir", return_value=tmp_path)
    return tmp_path


@pytest.fixture
def shell(mocker: MockerFixture) -> Mock:
    """A fake WScript.Shell whose shortcut.Save() writes an empty .lnk so existence checks work."""
    shortcut = Mock()
    fake_shell = Mock()

    def create_shortcut(path: str) -> Mock:
        shortcut.Save.side_effect = lambda: Path(path).write_bytes(b"")
        return shortcut

    fake_shell.CreateShortcut.side_effect = create_shortcut
    mocker.patch("core.autostart.Dispatch", return_value=fake_shell)
    return shortcut


def test_is_autostart_enabled_false_without_shortcut(startup_dir: Path) -> None:
    assert not autostart.is_autostart_enabled()


def test_enable_autostart_creates_shortcut(startup_dir: Path, shell: Mock) -> None:
    autostart.enable_autostart()
    assert autostart.is_autostart_enabled()
    assert (startup_dir / "Nimbus.lnk").exists()


def test_enable_autostart_runs_main_with_windowless_python(
    startup_dir: Path, shell: Mock, mocker: MockerFixture
) -> None:
    mocker.patch("core.autostart.is_frozen", return_value=False)
    autostart.enable_autostart()
    assert shell.TargetPath == str(Path(sys.executable).with_name("pythonw.exe"))
    assert shell.Arguments == f'"{autostart.ENTRY_SCRIPT}"'
    assert shell.WorkingDirectory == str(autostart.REPO_ROOT)


def test_enable_autostart_targets_executable_when_frozen(startup_dir: Path, shell: Mock, mocker: MockerFixture) -> None:
    mocker.patch("core.autostart.is_frozen", return_value=True)
    autostart.enable_autostart()
    assert shell.TargetPath == sys.executable
    assert shell.Arguments == ""


def test_enable_autostart_wraps_com_failure(startup_dir: Path, mocker: MockerFixture) -> None:
    mocker.patch("core.autostart.Dispatch", side_effect=com_error(-1, "denied", None, None))
    with pytest.raises(AutostartError, match="startup shortcut"):
        autostart.enable_autostart()


def test_disable_autostart_removes_shortcut(startup_dir: Path, shell: Mock) -> None:
    autostart.enable_autostart()
    autostart.disable_autostart()
    assert not autostart.is_autostart_enabled()


def test_disable_autostart_ignores_missing_shortcut(startup_dir: Path) -> None:
    autostart.disable_autostart()
    assert not autostart.is_autostart_enabled()


def test_disable_autostart_wraps_os_error(startup_dir: Path, mocker: MockerFixture) -> None:
    mocker.patch("pathlib.Path.unlink", side_effect=PermissionError("in use"))
    with pytest.raises(AutostartError, match="Couldn't remove"):
        autostart.disable_autostart()


def test_startup_dir_raises_without_appdata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APPDATA", raising=False)
    with pytest.raises(AutostartError, match="APPDATA"):
        autostart._startup_dir()


def test_startup_dir_uses_roaming_startup_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert autostart._startup_dir() == tmp_path / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
