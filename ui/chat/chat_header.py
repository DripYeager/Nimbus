"""
The chat window's sky header: the cloud logo and wordmark, an indexing status line with its
power-level bar, the Local/Cloud privacy badge, and the new-chat / history / settings / close
buttons. Dragging the header moves the window. Emits button signals; owns no chat state.
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from models.schema import IndexStatus
from ui.status_text import describe_status
from ui.theme.painting import CloudGlyph, PowerBar, SkyHeader
from ui.theme.tokens import HEADER_HEIGHT

LOGO_SIZE = 40
POWER_BAR_WIDTH = 140
BADGE_HEIGHT = 20


class ChatHeader(SkyHeader):
    """Title bar of the chat window."""

    new_chat_clicked = pyqtSignal()
    history_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    close_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(HEADER_HEIGHT)
        self._drag_offset: QPoint | None = None
        self._status = QLabel("Starting up…", self)
        self._status.setObjectName("HeaderStatus")
        self._power = PowerBar(self)
        self._power.setFixedWidth(POWER_BAR_WIDTH)
        self._badge = QLabel(self)
        self._badge.setObjectName("PrivacyBadge")
        self._badge.setFixedHeight(BADGE_HEIGHT)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 8, 10, 8)
        row.addWidget(CloudGlyph(LOGO_SIZE, self))
        row.addLayout(self._title_column())
        row.addStretch()
        row.addWidget(self._badge, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addSpacing(6)
        for icon, tip, signal in (
            ("+", "New chat (Ctrl+N)", self.new_chat_clicked),
            ("☰", "Chat history", self.history_clicked),
            ("⚙︎", "Settings", self.settings_clicked),
            ("✕", "Hide (Esc)", self.close_clicked),
        ):
            row.addWidget(_header_button(icon, tip, signal, self))
        self.set_privacy(is_cloud=False)

    def set_status(self, status: IndexStatus) -> None:
        """Shows indexing progress; the power bar only appears while there's work left."""
        self._status.setText(describe_status(status))
        self._power.set_ratio(status.progress_ratio)
        self._power.setVisible(status.is_busy and not status.is_paused)

    def set_privacy(self, is_cloud: bool) -> None:
        """Local (green) when answers are generated on this PC, Cloud (orange) otherwise."""
        self._badge.setText("● Cloud" if is_cloud else "● Local")
        self._badge.setToolTip(
            "Questions and file excerpts are sent to your cloud model provider."
            if is_cloud
            else "Everything stays on this PC."
        )
        self._badge.setProperty("cloud", "true" if is_cloud else "false")
        self._badge.style().unpolish(self._badge)
        self._badge.style().polish(self._badge)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.window().pos()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None

    def _title_column(self) -> QVBoxLayout:
        """Wordmark on top, status line and power bar underneath."""
        title = QLabel("NIMBUS", self)
        title.setObjectName("HeaderTitle")
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_row.addWidget(self._status)
        status_row.addWidget(self._power, alignment=Qt.AlignmentFlag.AlignVCenter)
        column = QVBoxLayout()
        column.setSpacing(0)
        column.addWidget(title)
        column.addLayout(status_row)
        return column


def _header_button(icon: str, tooltip: str, signal: pyqtSignal, parent: QWidget) -> QToolButton:
    button = QToolButton(parent)
    button.setObjectName("HeaderButton")
    button.setText(icon)
    button.setToolTip(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.clicked.connect(signal)
    return button
