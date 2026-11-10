from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from pytest_mock import MockerFixture

from core.exceptions import HotkeyError
from ui.api_client import ApiClient
from ui.desktop_shell import DesktopShell, _readable


class Collaborators(SimpleNamespace):
    chat: MagicMock
    tray: MagicMock
    hotkey: MagicMock
    instances: MagicMock
    wizard_cls: MagicMock
    settings: SimpleNamespace


@pytest.fixture
def parts(mocker: MockerFixture) -> Collaborators:
    """Every heavy UI piece the shell composes, replaced so no window, tray or hotkey is real."""
    settings = SimpleNamespace(hotkey="<ctrl>+<space>", onboarding_complete=True)
    mocker.patch("ui.desktop_shell.get_settings", return_value=settings)
    hotkey = mocker.patch("ui.desktop_shell.HotkeyListener").return_value
    hotkey.hotkey = "<ctrl>+<space>"
    return Collaborators(
        chat=mocker.patch("ui.desktop_shell.ChatWindow").return_value,
        tray=mocker.patch("ui.desktop_shell.TrayIcon").return_value,
        hotkey=hotkey,
        instances=mocker.patch("ui.desktop_shell.InstanceServer").return_value,
        wizard_cls=mocker.patch("ui.desktop_shell.OnboardingWizard"),
        settings=settings,
    )


@pytest.fixture
def on_quit() -> Mock:
    return Mock()


@pytest.fixture
def shell(parts: Collaborators, on_quit: Mock) -> DesktopShell:
    return DesktopShell(Mock(spec=ApiClient), on_quit=on_quit)


def test_start_sets_up_the_chat_and_tray(shell: DesktopShell, parts: Collaborators) -> None:
    shell.start()

    parts.chat.setup.assert_called_once()
    parts.tray.setup.assert_called_once()


def test_start_listens_for_second_launches(shell: DesktopShell, parts: Collaborators) -> None:
    shell.start()

    parts.instances.listen.assert_called_once()
    parts.instances.summon_requested.connect.assert_called_once_with(parts.chat.summon)


def test_start_wires_the_hotkey_to_toggle_the_chat(shell: DesktopShell, parts: Collaborators) -> None:
    shell.start()

    parts.hotkey.summoned.connect.assert_called_once_with(parts.chat.toggle)
    parts.hotkey.start.assert_called_once()


def test_start_wires_tray_quit_to_on_quit(shell: DesktopShell, parts: Collaborators, on_quit: Mock) -> None:
    shell.start()

    parts.tray.quit_requested.connect.assert_called_once_with(on_quit)


def test_start_announces_readiness_once_onboarded(shell: DesktopShell, parts: Collaborators) -> None:
    shell.start()

    parts.tray.notify.assert_called_once_with("Nimbus is ready. Press Ctrl+Space to summon me.")
    parts.wizard_cls.assert_not_called()


def test_start_runs_onboarding_on_first_launch(shell: DesktopShell, parts: Collaborators) -> None:
    parts.settings.onboarding_complete = False

    shell.start()

    parts.wizard_cls.return_value.show.assert_called_once()
    parts.tray.notify.assert_not_called()


def test_start_reports_a_hotkey_clash_in_the_tray(shell: DesktopShell, parts: Collaborators) -> None:
    parts.hotkey.start.side_effect = HotkeyError("'<ctrl>+<space>' is already used by another app.")

    shell.start()

    first_message = parts.tray.notify.call_args_list[0].args[0]
    assert first_message.startswith("'<ctrl>+<space>' is already used by another app.")
    assert "from the tray icon" in first_message


def test_finish_onboarding_summons_the_chat(shell: DesktopShell, parts: Collaborators) -> None:
    parts.settings.onboarding_complete = False
    shell.start()

    shell._finish_onboarding()

    parts.chat.summon.assert_called_once()
    assert shell._wizard is None


def test_open_settings_summons_the_chat_window_on_its_settings_page(shell: DesktopShell, parts: Collaborators) -> None:
    shell.open_settings()

    parts.chat.summon.assert_called_once()
    parts.chat.show_settings.assert_called_once()


def test_tray_settings_item_opens_the_settings_page(shell: DesktopShell, parts: Collaborators) -> None:
    shell.start()
    handler = parts.tray.settings_requested.connect.call_args.args[0]

    handler()

    parts.chat.show_settings.assert_called_once()


def test_settings_changed_rebinds_a_new_hotkey(shell: DesktopShell, parts: Collaborators) -> None:
    shell.start()
    parts.settings.hotkey = "<alt>+n"

    shell.settings_changed.emit()

    parts.hotkey.rebind.assert_called_once_with("<alt>+n")
    parts.tray.notify.assert_called_with("Hotkey changed to Alt+N.")


def test_settings_changed_leaves_an_unchanged_hotkey_alone(shell: DesktopShell, parts: Collaborators) -> None:
    shell.start()

    shell.settings_changed.emit()

    parts.hotkey.rebind.assert_not_called()


def test_settings_changed_reports_a_failed_rebind(shell: DesktopShell, parts: Collaborators) -> None:
    shell.start()
    parts.settings.hotkey = "<alt>+n"
    parts.hotkey.rebind.side_effect = HotkeyError("'<alt>+n' is already used by another app.")

    shell.settings_changed.emit()

    parts.tray.notify.assert_called_with("'<alt>+n' is already used by another app.")


def test_stop_releases_the_hotkey_and_hides_everything(shell: DesktopShell, parts: Collaborators) -> None:
    shell.stop()

    parts.hotkey.stop.assert_called_once()
    parts.tray.hide.assert_called_once()
    parts.chat.hide.assert_called_once()


@pytest.mark.parametrize(
    ("hotkey", "expected"),
    [("<ctrl>+<space>", "Ctrl+Space"), ("<ctrl>+<shift>+n", "Ctrl+Shift+N"), ("<alt>+<f2>", "Alt+F2")],
)
def test_readable_formats_hotkeys_for_messages(hotkey: str, expected: str) -> None:
    assert _readable(hotkey) == expected
