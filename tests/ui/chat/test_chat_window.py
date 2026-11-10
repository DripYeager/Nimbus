from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest
from PyQt6.QtCore import QAbstractAnimation, QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QPushButton, QToolButton, QWidget
from pytest_mock import MockerFixture

from models.api import SettingsView
from models.schema import IndexStatus
from ui.api_client import ApiClient
from ui.chat.chat_window import CHAT_PAGE, SETTINGS_PAGE, STATUS_POLL_MS, ChatWindow


def _synchronous(fn: Any, ok: Any, err: Any = None) -> None:
    ok(fn())


class FakeSettingsPanel(QWidget):
    """Stands in for the real Settings page, which has its own tests."""

    back_requested = pyqtSignal()
    saved = pyqtSignal()

    def __init__(self, api: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.loads = 0

    def load(self) -> None:
        self.loads += 1


@pytest.fixture
def api(mocker: MockerFixture) -> Mock:
    fake = mocker.Mock(spec=ApiClient)
    fake.index_status.return_value = IndexStatus(cataloged_files=321)
    fake.settings.return_value = SettingsView(values={}, has_api_key={}, data_dir="C:/data", is_cloud=True)
    fake.conversations.return_value = []
    return fake


@pytest.fixture
def stream(mocker: MockerFixture) -> MagicMock:
    """The chat stream would open a real HTTP connection; nothing here should reach the network."""
    return mocker.patch("ui.chat.chat_window.ChatStream").return_value


@pytest.fixture
def window(mocker: MockerFixture, api: Mock, stream: MagicMock) -> Iterator[ChatWindow]:
    mocker.patch("ui.chat.chat_window.run_in_background", side_effect=_synchronous)
    mocker.patch("ui.chat.history_panel.run_in_background", side_effect=_synchronous)
    mocker.patch("ui.chat.chat_session.run_in_background", side_effect=_synchronous)
    mocker.patch("ui.chat.chat_window.SettingsPanel", FakeSettingsPanel)
    chat_window = ChatWindow(api)
    chat_window.setup()
    yield chat_window
    chat_window._status_timer.stop()
    chat_window.hide()
    chat_window.deleteLater()


def _header_button(window: ChatWindow, tooltip_start: str) -> QToolButton:
    return next(b for b in window._header.findChildren(QToolButton) if b.toolTip().startswith(tooltip_start))


def _finish_animation(window: ChatWindow) -> None:
    window._animation.setCurrentTime(window._animation.totalDuration())


def test_setup_makes_a_frameless_always_on_top_window(window: ChatWindow) -> None:
    flags = window.windowFlags()

    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    assert window.windowTitle() == "Nimbus"


def test_summon_shows_the_window_with_the_glide_in(window: ChatWindow) -> None:
    window.summon()

    assert window.isVisible()
    assert window._animation.state() == QAbstractAnimation.State.Running


def test_summon_polls_status_into_the_header(window: ChatWindow) -> None:
    window.summon()

    assert window._header._status.text() == "Ready · 321 files known"
    assert window._header._badge.text() == "●  Cloud"
    assert window._status_timer.interval() == STATUS_POLL_MS


def test_summon_while_visible_keeps_the_position(window: ChatWindow) -> None:
    window.summon()
    _finish_animation(window)
    position = window.pos()

    window.summon()

    assert window.pos() == position


def test_dismiss_hides_once_the_animation_ends(window: ChatWindow) -> None:
    window.summon()
    _finish_animation(window)

    window.dismiss()
    _finish_animation(window)

    assert not window.isVisible()
    assert not window._status_timer.isActive()


def test_dismiss_does_nothing_when_hidden(window: ChatWindow) -> None:
    window.dismiss()

    assert window._animation is None


def test_toggle_summons_a_hidden_window(window: ChatWindow) -> None:
    window.toggle()

    assert window.isVisible()


def test_toggle_dismisses_the_window_in_front(mocker: MockerFixture, window: ChatWindow) -> None:
    window.summon()
    mocker.patch.object(window, "isActiveWindow", return_value=True)
    dismiss = mocker.patch.object(window, "dismiss")

    window.toggle()

    dismiss.assert_called_once()


def test_toggle_brings_a_background_window_forward(mocker: MockerFixture, window: ChatWindow) -> None:
    window.summon()
    mocker.patch.object(window, "isActiveWindow", return_value=False)
    summon = mocker.patch.object(window, "summon")

    window.toggle()

    summon.assert_called_once()


def test_escape_dismisses_the_window(mocker: MockerFixture, window: ChatWindow) -> None:
    dismiss = mocker.patch.object(window, "dismiss")

    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))

    dismiss.assert_called_once()


def test_other_keys_do_not_dismiss(mocker: MockerFixture, window: ChatWindow) -> None:
    dismiss = mocker.patch.object(window, "dismiss")

    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier))

    dismiss.assert_not_called()


def test_minimize_button_hides_the_window_and_keeps_the_page(window: ChatWindow) -> None:
    window.summon()
    _finish_animation(window)
    window.show_settings()

    [b for b in window._header.findChildren(QToolButton) if b.toolTip().startswith("Minimize")][-1].click()
    _finish_animation(window)

    assert (window.isVisible(), window._pages.currentIndex()) == (False, SETTINGS_PAGE)


def test_close_button_hides_the_window_and_returns_to_the_chat(window: ChatWindow) -> None:
    window.summon()
    _finish_animation(window)
    window.show_settings()

    [b for b in window._header.findChildren(QToolButton) if b.toolTip().startswith("Close")][-1].click()
    _finish_animation(window)

    assert (window.isVisible(), window._pages.currentIndex()) == (False, CHAT_PAGE)


def test_settings_button_opens_settings_inside_the_window(window: ChatWindow) -> None:
    _header_button(window, "Settings").click()

    assert window._pages.currentIndex() == SETTINGS_PAGE
    assert window._settings.loads == 1


def test_back_button_returns_from_settings_to_the_chat(window: ChatWindow) -> None:
    window.show_settings()

    _header_button(window, "Back to chat").click()

    assert window._pages.currentIndex() == CHAT_PAGE


def test_escape_on_settings_goes_back_instead_of_hiding(window: ChatWindow) -> None:
    window.summon()
    _finish_animation(window)
    window.show_settings()

    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))

    assert window._pages.currentIndex() == CHAT_PAGE
    assert window.isVisible()


def test_saving_settings_refreshes_the_privacy_badge(window: ChatWindow, api: Mock) -> None:
    api.index_status.reset_mock()

    window._settings.saved.emit()

    api.index_status.assert_called_once()


def test_history_button_shows_the_history_page(window: ChatWindow, api: Mock) -> None:
    _header_button(window, "Chat history").click()

    assert window._pages.currentIndex() == 1
    api.conversations.assert_called_once()


def test_history_back_returns_to_the_chat(window: ChatWindow) -> None:
    _header_button(window, "Chat history").click()

    _header_button(window, "Back to chat").click()

    assert window._pages.currentIndex() == CHAT_PAGE


def test_opening_a_saved_chat_loads_it(window: ChatWindow, api: Mock) -> None:
    _header_button(window, "Chat history").click()
    api.conversation.return_value = []

    window._history.opened.emit("c3")

    assert window._pages.currentIndex() == 0
    api.conversation.assert_called_once_with("c3")


def test_new_chat_button_resets_the_conversation(window: ChatWindow, stream: MagicMock) -> None:
    window._view.add_user_message("hello")

    _header_button(window, "New chat").click()

    stream.cancel.assert_not_called()
    assert window._view.currentIndex() == 0


def test_ask_summons_and_sends(window: ChatWindow, stream: MagicMock) -> None:
    window.ask("How's my battery?")

    assert window.isVisible()
    stream.send.assert_called_once_with("How's my battery?", None, None)


def test_poll_status_ignores_errors(mocker: MockerFixture, window: ChatWindow) -> None:
    mocker.patch("ui.chat.chat_window.run_in_background", side_effect=lambda fn, ok, err: err("down"))

    window._poll_status()

    assert window._header._status.text() == "Starting up…"


def test_summon_during_dismiss_brings_the_window_back(window: ChatWindow) -> None:
    window.summon()
    _finish_animation(window)
    window.dismiss()
    window._animation.setCurrentTime(window._animation.totalDuration() // 2)

    window.summon()
    _finish_animation(window)

    assert window.isVisible()


def test_switching_pages_never_shifts_the_layout(window: ChatWindow) -> None:
    """A layout shift in this translucent window left the old header on screen after Back."""
    assert window._hint.sizePolicy().retainSizeWhenHidden()


def test_switching_pages_repaints_the_whole_window(window: ChatWindow, mocker: MockerFixture) -> None:
    repaint = mocker.patch.object(window, "update")

    window.show_settings()
    window.show_chat()

    assert repaint.call_count == 2


def test_ask_about_file_opens_a_new_chat_with_the_file_attached(window: ChatWindow) -> None:
    window.ask_about_file("C:/Docs/Q3 report.pdf")

    assert window.isVisible()
    assert [b.text() for b in window._attachments.findChildren(QPushButton)][0] == "Q3 report.pdf"


def test_capture_screen_hides_the_window_first(window: ChatWindow, mocker: MockerFixture) -> None:
    later = mocker.patch("ui.chat.chat_window.QTimer.singleShot")
    window.summon()

    window.capture_screen()

    assert not window.isVisible()
    later.assert_called_once()
