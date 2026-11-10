from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from core.exceptions import ExplorerMenuError
from core.explorer_menu import (
    COMMAND_KEY,
    MENU_TEXT,
    VERB_KEY,
    disable_explorer_menu,
    enable_explorer_menu,
    explorer_command,
    is_explorer_menu_enabled,
)


@pytest.fixture
def registry(mocker: MockerFixture) -> MagicMock:
    """A stand-in for winreg, so no test touches the real registry."""
    fake = mocker.patch("core.explorer_menu.winreg")
    fake.HKEY_CURRENT_USER = "HKCU"
    fake.REG_SZ = 1
    return fake


def test_explorer_command_passes_the_clicked_file_after_ask(mocker: MockerFixture) -> None:
    mocker.patch("core.explorer_menu.launch_command", return_value=("C:/Nimbus/Nimbus.exe", ""))

    assert explorer_command() == '"C:/Nimbus/Nimbus.exe" --ask "%1"'


def test_explorer_command_runs_the_script_from_a_source_checkout(mocker: MockerFixture) -> None:
    mocker.patch("core.explorer_menu.launch_command", return_value=("C:/py/pythonw.exe", '"C:/Nimbus/main.py"'))

    assert explorer_command() == '"C:/py/pythonw.exe" "C:/Nimbus/main.py" --ask "%1"'


def test_enable_explorer_menu_writes_the_verb_and_its_command(registry: MagicMock) -> None:
    enable_explorer_menu()

    created = [call.args[1] for call in registry.CreateKey.call_args_list]
    values = [call.args[1:] for call in registry.SetValueEx.call_args_list]
    assert created == [VERB_KEY, COMMAND_KEY]
    assert ("MUIVerb", 0, 1, MENU_TEXT) in values


def test_enable_explorer_menu_raises_when_windows_refuses(registry: MagicMock) -> None:
    registry.CreateKey.side_effect = PermissionError("denied")

    with pytest.raises(ExplorerMenuError, match="Couldn't add"):
        enable_explorer_menu()


def test_disable_explorer_menu_removes_the_command_before_the_verb(registry: MagicMock) -> None:
    disable_explorer_menu()

    assert [call.args[1] for call in registry.DeleteKey.call_args_list] == [COMMAND_KEY, VERB_KEY]


def test_disable_explorer_menu_ignores_a_missing_entry(registry: MagicMock) -> None:
    registry.DeleteKey.side_effect = FileNotFoundError

    disable_explorer_menu()


def test_is_explorer_menu_enabled_is_false_without_the_key(registry: MagicMock) -> None:
    registry.OpenKey.side_effect = FileNotFoundError

    assert is_explorer_menu_enabled() is False
