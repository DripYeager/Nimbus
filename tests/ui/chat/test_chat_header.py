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


def test_chat_header_starts_as_local(header: ChatHeader) -> None:
    assert (header._badge.text(), header._badge.property("cloud")) == ("● Local", "false")


def test_set_privacy_shows_the_cloud_badge(header: ChatHeader) -> None:
    header.set_privacy(is_cloud=True)

    assert (header._badge.text(), header._badge.property("cloud")) == ("● Cloud", "true")
    assert "cloud model provider" in header._badge.toolTip()


def test_set_status_shows_the_status_line(header: ChatHeader) -> None:
    header.set_status(IndexStatus(cataloged_files=12))

    assert header._status.text() == "Ready · 12 files known"


def test_set_status_shows_the_power_bar_while_indexing(header: ChatHeader) -> None:
    header.set_status(IndexStatus(content_files=10, indexed_files=4, pending_files=6))

    assert not header._power.isHidden()
    assert header._power._ratio == pytest.approx(0.4)


def test_set_status_hides_the_power_bar_when_idle(header: ChatHeader) -> None:
    header.set_status(IndexStatus(content_files=10, indexed_files=10))

    assert header._power.isHidden()


def test_set_status_hides_the_power_bar_while_paused(header: ChatHeader) -> None:
    header.set_status(IndexStatus(content_files=10, indexed_files=4, pending_files=6, is_paused=True))

    assert header._power.isHidden()


@pytest.mark.parametrize(
    ("tooltip", "signal_name"),
    [
        ("New chat", "new_chat_clicked"),
        ("Chat history", "history_clicked"),
        ("Settings", "settings_clicked"),
        ("Hide", "close_clicked"),
    ],
)
def test_header_buttons_emit_their_signal(header: ChatHeader, tooltip: str, signal_name: str) -> None:
    received: list[None] = []
    getattr(header, signal_name).connect(lambda: received.append(None))

    _button(header, tooltip).click()

    assert received == [None]


def test_dragging_the_header_moves_the_window(header: ChatHeader) -> None:
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
