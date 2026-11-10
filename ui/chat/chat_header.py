"""
The chat window's sky header. On the chat page: the cloud logo and comic-style wordmark, a
status line (or a scouter-style power-level readout while files are being learned), the
Local/Cloud badge, and icon buttons for new chat, history, settings and hide. On a sub-page
(Settings, History): a back arrow and the page title. Dragging it moves the window. Emits
signals only; owns no chat state.
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent
from PyQt6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from models.schema import IndexStatus
from ui.status_text import describe_status
from ui.theme.energy import PowerLevelReadout
from ui.theme.fonts import use_display_font
from ui.theme.line_icons import line_icon
from ui.theme.painting import CloudGlyph, SkyHeader
from ui.theme.tokens import HEADER_HEIGHT

LOGO_SIZE = 44
ICON_SIZE = 18
WORDMARK_PX = 30
BADGE_HEIGHT = 24
PAGE_TITLE_PX = 26
WHITE = "#FFFFFF"


class ChatHeader(SkyHeader):
    """Title bar of the chat window."""

    new_chat_clicked = pyqtSignal()
    history_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    close_clicked = pyqtSignal()
    back_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(HEADER_HEIGHT)
        self._drag_offset: QPoint | None = None
        self._status = QLabel("Starting up…", self)
        self._status.setObjectName("HeaderStatus")
        self._power = PowerLevelReadout(self)
        self._power.hide()
        self._badge = QLabel(self)
        self._badge.setObjectName("PrivacyBadge")
        self._badge.setFixedHeight(BADGE_HEIGHT)
        self._page_title = QLabel(self)
        self._page_title.setObjectName("HeaderPageTitle")
        use_display_font(self._page_title, PAGE_TITLE_PX)
        self._modes = QStackedWidget(self)
        self._modes.addWidget(self._chat_mode())
        self._modes.addWidget(self._page_mode())
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 8, 12, 8)
        row.addWidget(self._modes)
        self.set_privacy(is_cloud=False)

    def show_page(self, title: str | None) -> None:
        """None shows the chat header; a title shows the back-arrow header for a sub-page."""
        if title is None:
            self._modes.setCurrentIndex(0)
            return
        self._page_title.setText(title.upper())
        self._modes.setCurrentIndex(1)

    def set_status(self, status: IndexStatus) -> None:
        """A plain status line normally; the power-level readout while files are being learned."""
        busy = status.is_busy and not status.is_paused
        self._status.setText(describe_status(status))
        self._status.setVisible(not busy)
        self._power.setVisible(busy)
        self._power.set_progress(status.indexed_files, status.progress_ratio)
        self._power.setToolTip(describe_status(status))

    def set_privacy(self, is_cloud: bool) -> None:
        """Local (green) when answers are generated on this PC, Cloud (orange) otherwise."""
        self._badge.setText("●  Cloud" if is_cloud else "●  Local")
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

    def _chat_mode(self) -> QWidget:
        """Logo, wordmark + status, badge and the four header buttons."""
        mode = QWidget(self)
        row = QHBoxLayout(mode)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(CloudGlyph(LOGO_SIZE, mode))
        row.addLayout(self._title_column(mode))
        row.addStretch()
        row.addWidget(self._badge, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addSpacing(6)
        for icon, tip, signal in (
            ("plus", "New chat (Ctrl+N)", self.new_chat_clicked),
            ("history", "Chat history", self.history_clicked),
            ("settings", "Settings", self.settings_clicked),
            ("x", "Hide (Esc)", self.close_clicked),
        ):
            row.addWidget(_header_button(icon, tip, signal, mode))
        return mode

    def _page_mode(self) -> QWidget:
        """Back arrow, page title, and hide."""
        mode = QWidget(self)
        row = QHBoxLayout(mode)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(_header_button("arrow-left", "Back to chat (Esc)", self.back_clicked, mode))
        row.addWidget(self._page_title)
        row.addStretch()
        row.addWidget(_header_button("x", "Hide", self.close_clicked, mode))
        return mode

    def _title_column(self, parent: QWidget) -> QVBoxLayout:
        """The comic-style NIMBUS wordmark with a soft orange glow, and the status under it."""
        title = QLabel("NIMBUS", parent)
        title.setObjectName("HeaderWordmark")
        use_display_font(title, WORDMARK_PX)
        glow = QGraphicsDropShadowEffect(title)
        glow.setBlurRadius(14)
        glow.setOffset(0, 2)
        glow.setColor(QColor(255, 120, 20, 170))
        title.setGraphicsEffect(glow)
        column = QVBoxLayout()
        column.setSpacing(0)
        column.addWidget(title)
        column.addWidget(self._status)
        column.addWidget(self._power)
        return column


def _header_button(icon: str, tooltip: str, signal: pyqtSignal, parent: QWidget) -> QToolButton:
    button = QToolButton(parent)
    button.setObjectName("HeaderButton")
    button.setIcon(line_icon(icon, WHITE, ICON_SIZE))
    button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
    button.setToolTip(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.clicked.connect(signal)
    return button
