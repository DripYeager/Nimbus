from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import Mock

import pytest
from PyQt6.QtGui import QAction, QIcon, QImage
from PyQt6.QtWidgets import QSystemTrayIcon
from pytest_mock import MockerFixture

from core.exceptions import NimbusError
from models.schema import IndexStatus
from ui.api_client import ApiClient
from ui.tray import MENU_ICON_SIZE, TOOLTIP_TITLE, TrayIcon, _menu_icon


def _synchronous(fn: Any, ok: Any, err: Any = None) -> None:
    """run_in_background without the thread pool, including the error path."""
    try:
        result = fn()
    except NimbusError as e:
        if err is not None:
            err(str(e))
        return
    ok(result)


@pytest.fixture
def api(mocker: MockerFixture) -> Mock:
    fake = mocker.Mock(spec=ApiClient)
    fake.index_status.return_value = IndexStatus(cataloged_files=40)
    fake.set_paused.return_value = IndexStatus(is_paused=True)
    fake.rebuild_index.return_value = IndexStatus(is_scanning=True)
    return fake


@pytest.fixture
def tray(mocker: MockerFixture, api: Mock) -> Iterator[TrayIcon]:
    mocker.patch("ui.tray.run_in_background", side_effect=_synchronous)
    tray_icon = TrayIcon(api)
    tray_icon.setup()
    yield tray_icon
    tray_icon.hide()


def _action(tray_icon: TrayIcon, text: str) -> QAction:
    return next(a for a in tray_icon._menu.actions() if a.text() == text)


def _image(icon: QIcon) -> QImage:
    return icon.pixmap(MENU_ICON_SIZE, MENU_ICON_SIZE).toImage()


def test_setup_builds_the_full_menu(tray: TrayIcon) -> None:
    texts = [a.text() for a in tray._menu.actions() if not a.isSeparator()]

    assert texts == [
        "Open Nimbus",
        "Ask about something on screen",
        "Ready · 40 files known",
        "Pause indexing",
        "Rebuild index",
        "Settings…",
        "Quit Nimbus",
    ]


def test_setup_gives_every_menu_item_an_icon(tray: TrayIcon) -> None:
    assert all(not a.icon().isNull() for a in tray._menu.actions() if not a.isSeparator())


def test_setup_shows_the_pause_icon_while_indexing_runs(tray: TrayIcon) -> None:
    assert _image(tray._pause_action.icon()) == _image(_menu_icon("pause"))


def test_setup_shows_the_current_status_in_the_tooltip(tray: TrayIcon) -> None:
    assert tray._tray.toolTip() == f"{TOOLTIP_TITLE}: Ready · 40 files known"


def test_setup_keeps_the_status_line_disabled(tray: TrayIcon) -> None:
    assert not tray._status_action.isEnabled()


def test_setup_starts_status_polling(tray: TrayIcon) -> None:
    assert tray._timer.isActive()


def test_refresh_status_ignores_errors(tray: TrayIcon, api: Mock) -> None:
    api.index_status.side_effect = NimbusError("down")

    tray.refresh_status()

    assert tray._status_action.text() == "Ready · 40 files known"


def test_open_action_emits_summon_requested(tray: TrayIcon) -> None:
    received: list[None] = []
    tray.summon_requested.connect(lambda: received.append(None))

    _action(tray, "Open Nimbus").trigger()

    assert received == [None]


def test_settings_action_emits_settings_requested(tray: TrayIcon) -> None:
    received: list[None] = []
    tray.settings_requested.connect(lambda: received.append(None))

    _action(tray, "Settings…").trigger()

    assert received == [None]


def test_quit_action_emits_quit_requested(tray: TrayIcon) -> None:
    received: list[None] = []
    tray.quit_requested.connect(lambda: received.append(None))

    _action(tray, "Quit Nimbus").trigger()

    assert received == [None]


def test_toggle_pause_pauses_and_relabels_the_item(tray: TrayIcon, api: Mock) -> None:
    _action(tray, "Pause indexing").trigger()

    api.set_paused.assert_called_once_with(True)
    assert tray._pause_action.text() == "Resume indexing"


def test_toggle_pause_flips_the_icon_to_play(tray: TrayIcon) -> None:
    _action(tray, "Pause indexing").trigger()

    assert _image(tray._pause_action.icon()) == _image(_menu_icon("play"))


def test_toggle_pause_resumes_when_paused(tray: TrayIcon, api: Mock) -> None:
    _action(tray, "Pause indexing").trigger()
    api.set_paused.return_value = IndexStatus()

    tray._pause_action.trigger()

    api.set_paused.assert_called_with(False)
    assert tray._pause_action.text() == "Pause indexing"


def test_toggle_pause_notifies_on_error(mocker: MockerFixture, tray: TrayIcon, api: Mock) -> None:
    api.set_paused.side_effect = NimbusError("Engine is busy")
    notify = mocker.patch.object(tray, "notify")

    tray._pause_action.trigger()

    notify.assert_called_once_with("Engine is busy")


def test_rebuild_notifies_and_shows_the_new_status(mocker: MockerFixture, tray: TrayIcon) -> None:
    notify = mocker.patch.object(tray, "notify")

    _action(tray, "Rebuild index").trigger()

    notify.assert_called_once_with("Re-reading all your files in the background.")
    assert tray._status_action.text() == "Looking for new files…"


def test_rebuild_notifies_on_error(mocker: MockerFixture, tray: TrayIcon, api: Mock) -> None:
    api.rebuild_index.side_effect = NimbusError("Can't rebuild now")
    notify = mocker.patch.object(tray, "notify")

    _action(tray, "Rebuild index").trigger()

    notify.assert_called_once_with("Can't rebuild now")


@pytest.mark.parametrize(
    "reason", [QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick]
)
def test_handle_activated_summons_on_click(tray: TrayIcon, reason: QSystemTrayIcon.ActivationReason) -> None:
    received: list[None] = []
    tray.summon_requested.connect(lambda: received.append(None))

    tray._handle_activated(reason)

    assert received == [None]


def test_handle_activated_ignores_the_context_menu_click(tray: TrayIcon) -> None:
    received: list[None] = []
    tray.summon_requested.connect(lambda: received.append(None))

    tray._handle_activated(QSystemTrayIcon.ActivationReason.Context)

    assert received == []


def test_notify_shows_a_balloon(mocker: MockerFixture, tray: TrayIcon) -> None:
    show_message = mocker.patch.object(tray._tray, "showMessage")

    tray.notify("Hello")

    assert show_message.call_args.args[:2] == (TOOLTIP_TITLE, "Hello")


def test_notify_does_nothing_before_setup(api: Mock) -> None:
    TrayIcon(api).notify("Hello")


def test_hide_stops_polling(tray: TrayIcon) -> None:
    tray.hide()

    assert not tray._timer.isActive()


def test_hide_is_safe_before_setup(api: Mock) -> None:
    TrayIcon(api).hide()
