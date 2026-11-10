from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QToolButton

from models.schema import IndexStatus
from ui.chat.chat_header import ChatHeader


@pytest.fixture
def header() -> ChatHeader:
    return ChatHeader()


def _mouse(kind: QEvent.Type, global_pos: QPoint, buttons: Qt.MouseButton) -> QMouseEvent:
    point = QPointF(global_pos)
    return QMouseEvent(kind, point, point, Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier)


def _button(header: ChatHeader, tooltip_start: str) -> QToolButton:
    return next(b for b in header.findChildren(QToolButton) if b.toolTip().startswith(tooltip_start))


def test_chat_header_starts_on_the_chat_mode(header: ChatHeader) -> None:
    assert header._modes.currentIndex() == 0


def test_chat_header_starts_as_local(header: ChatHeader) -> None:
    assert (header._badge.text(), header._badge.property("cloud")) == ("●  Local", "false")


def test_set_privacy_shows_the_cloud_badge(header: ChatHeader) -> None:
    header.set_privacy(is_cloud=True)

    assert (header._badge.text(), header._badge.property("cloud")) == ("●  Cloud", "true")


def test_set_privacy_explains_where_the_cloud_sends_data(header: ChatHeader) -> None:
    header.set_privacy(is_cloud=True)

    assert "cloud model provider" in header._badge.toolTip()


def test_show_page_switches_to_the_page_header_with_an_uppercase_title(header: ChatHeader) -> None:
    header.show_page("Settings")

    assert (header._modes.currentIndex(), header._page_title.text()) == (1, "SETTINGS")


def test_show_page_none_returns_to_the_chat_header(header: ChatHeader) -> None:
    header.show_page("History")

    header.show_page(None)

    assert header._modes.currentIndex() == 0


def test_back_button_emits_back_clicked(header: ChatHeader) -> None:
    received: list[None] = []
    header.back_clicked.connect(lambda: received.append(None))
    header.show_page("Settings")

    _button(header, "Back to chat").click()

    assert received == [None]


def test_page_mode_hide_button_emits_close_clicked(header: ChatHeader) -> None:
    received: list[None] = []
    header.close_clicked.connect(lambda: received.append(None))

    next(b for b in header.findChildren(QToolButton) if b.toolTip() == "Hide").click()

    assert received == [None]


def test_set_status_shows_the_status_line_when_idle(header: ChatHeader) -> None:
    header.set_status(IndexStatus(cataloged_files=12))

    assert (header._status.text(), header._status.isHidden(), header._power.isHidden()) == (
        "Ready · 12 files known",
        False,
        True,
    )


def test_set_status_shows_the_power_readout_while_indexing(header: ChatHeader) -> None:
    header.set_status(IndexStatus(content_files=10, indexed_files=4, pending_files=6))

    assert (header._power.isHidden(), header._status.isHidden()) == (False, True)


def test_set_status_feeds_the_progress_to_the_power_readout(header: ChatHeader) -> None:
    header.set_status(IndexStatus(content_files=10, indexed_files=4, pending_files=6))

    assert (header._power._value, header._power._ratio) == (4, pytest.approx(0.4))


def test_set_status_keeps_the_status_text_as_the_readout_tooltip(header: ChatHeader) -> None:
    header.set_status(IndexStatus(content_files=10, indexed_files=4, pending_files=6))

    assert header._power.toolTip() == "Learning your files · 4 of 10"


def test_set_status_hides_the_power_readout_while_paused(header: ChatHeader) -> None:
    header.set_status(IndexStatus(content_files=10, indexed_files=4, pending_files=6, is_paused=True))

    assert (header._power.isHidden(), header._status.text()) == (True, "Indexing paused")


@pytest.mark.parametrize(
    ("tooltip", "signal_name"),
    [
        ("New chat", "new_chat_clicked"),
        ("Chat history", "history_clicked"),
        ("Settings", "settings_clicked"),
        ("Hide (Esc)", "close_clicked"),
    ],
)
def test_chat_mode_buttons_emit_their_signal(header: ChatHeader, tooltip: str, signal_name: str) -> None:
    received: list[None] = []
    getattr(header, signal_name).connect(lambda: received.append(None))

    _button(header, tooltip).click()

    assert received == [None]


def test_mouse_move_after_a_press_drags_the_window(header: ChatHeader) -> None:
    header.move(100, 100)
    left = Qt.MouseButton.LeftButton

    header.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, QPoint(150, 120), left))
    header.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, QPoint(190, 160), left))

    assert header.pos() == QPoint(140, 140)


def test_mouse_move_without_a_press_does_not_move(header: ChatHeader) -> None:
    header.move(100, 100)

    header.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, QPoint(190, 160), Qt.MouseButton.LeftButton))

    assert header.pos() == QPoint(100, 100)


def test_mouse_release_ends_the_drag(header: ChatHeader) -> None:
    header.move(100, 100)
    left = Qt.MouseButton.LeftButton
    header.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, QPoint(150, 120), left))

    header.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, QPoint(150, 120), Qt.MouseButton.NoButton))
    header.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, QPoint(190, 160), left))

    assert header.pos() == QPoint(100, 100)
