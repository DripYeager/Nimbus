"""
The window the hotkey summons: a frameless, always-on-top panel with the sky header, the
conversation (or chat history), and the message box. Owns window behaviour — summon/dismiss
animation, placement, keyboard shortcuts, status polling — and composes the chat widgets.
"""

from __future__ import annotations

from PyQt6.QtCore import QAbstractAnimation, QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QGuiApplication, QKeyEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QSizeGrip,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from models.schema import IndexStatus
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.chat.chat_header import ChatHeader
from ui.chat.chat_input import ChatInput
from ui.chat.chat_session import ChatSession
from ui.chat.chat_stream import ChatStream
from ui.chat.chat_view import ChatView
from ui.chat.history_panel import HistoryPanel
from ui.theme.icons import app_icon
from ui.theme.motion import build_dismiss_animation, build_summon_animation, stop_animation
from ui.theme.tokens import CHAT_HEIGHT, CHAT_MIN_HEIGHT, CHAT_WIDTH, SHADOW_ALPHA, SHADOW_BLUR, SHADOW_MARGIN

STATUS_POLL_MS = 2000
# Placing the window a little above center keeps it clear of the taskbar on short screens.
VERTICAL_POSITION = 0.42
FOOTER_TEXT = "Enter to send · Shift+Enter for a new line · Esc to hide"


class ChatWindow(QWidget):
    """Emits settings_requested when the gear is clicked; everything else is handled here."""

    settings_requested = pyqtSignal()

    def __init__(self, api: ApiClient) -> None:
        super().__init__()
        self._api = api
        self._animation: QAbstractAnimation | None = None
        self._status_timer = QTimer(self)
        self._header = ChatHeader()
        self._view = ChatView()
        self._history = HistoryPanel(api)
        self._input = ChatInput()
        self._pages = QStackedWidget()
        self._session = ChatSession(self._view, self._input, api, ChatStream())

    def setup(self) -> None:
        """Builds the window and wires every signal."""
        self._configure_window()
        self._build_layout()
        self._session.connect_signals()
        self._session.status_received.connect(self._show_status)
        self._header.new_chat_clicked.connect(self._new_chat)
        self._header.history_clicked.connect(self._show_history)
        self._header.settings_clicked.connect(self.settings_requested)
        self._header.close_clicked.connect(self.dismiss)
        self._history.opened.connect(self._open_conversation)
        self._history.back.connect(lambda: self._pages.setCurrentIndex(0))
        self._status_timer.timeout.connect(self._poll_status)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._new_chat)

    def toggle(self) -> None:
        """The hotkey: summon if hidden or in the background, hide if already in front."""
        if self.isVisible() and self.isActiveWindow():
            self.dismiss()
        else:
            self.summon()

    def summon(self) -> None:
        """Shows the window on the screen under the mouse with the glide-in animation."""
        final_pos = self._placement()
        if self._is_dismissing():
            stop_animation(self._animation)
            self.hide()
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
            self._animation = build_summon_animation(self, final_pos, self._header)
            self._animation.start()
        self.raise_()
        self.activateWindow()
        self._input.focus()
        self._status_timer.start(STATUS_POLL_MS)
        self._poll_status()

    def dismiss(self) -> None:
        """Glides away and hides; the conversation is kept for next time."""
        if not self.isVisible():
            return
        self._status_timer.stop()
        stop_animation(self._animation)
        self._animation = build_dismiss_animation(self, self.pos())
        self._animation.finished.connect(self.hide)
        self._animation.start()

    def _is_dismissing(self) -> bool:
        return (
            self.isVisible()
            and self.windowOpacity() < 1.0
            and self._animation is not None
            and (self._animation.state() == QAbstractAnimation.State.Running)
        )

    def ask(self, text: str) -> None:
        """Summons the window and sends text straight away (used by tray shortcuts)."""
        self.summon()
        self._session.send(text)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss()
            return
        super().keyPressEvent(event)

    def _configure_window(self) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("Nimbus")
        self.setWindowIcon(app_icon())
        self.resize(CHAT_WIDTH + 2 * SHADOW_MARGIN, CHAT_HEIGHT + 2 * SHADOW_MARGIN)
        self.setMinimumHeight(CHAT_MIN_HEIGHT + 2 * SHADOW_MARGIN)

    def _build_layout(self) -> None:
        """Panel with a soft shadow: header, pages (chat / history), input, footer."""
        panel = QFrame(self)
        panel.setObjectName("ChatPanel")
        shadow = QGraphicsDropShadowEffect(panel)
        shadow.setBlurRadius(SHADOW_BLUR)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, SHADOW_ALPHA))
        panel.setGraphicsEffect(shadow)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
        outer.addWidget(panel)
        self._pages.addWidget(self._view)
        self._pages.addWidget(self._history)
        body = QVBoxLayout()
        body.setContentsMargins(16, 12, 16, 8)
        body.setSpacing(10)
        body.addWidget(self._pages, stretch=1)
        body.addWidget(self._input)
        body.addLayout(self._footer(panel))
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._header)
        column.addLayout(body, stretch=1)

    def _footer(self, panel: QWidget) -> QHBoxLayout:
        hint = QLabel(FOOTER_TEXT, panel)
        hint.setObjectName("FooterHint")
        row = QHBoxLayout()
        row.addWidget(hint)
        row.addStretch()
        row.addWidget(QSizeGrip(panel), alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        return row

    def _placement(self) -> QPoint:
        """Horizontally centered, a bit above middle, on the screen holding the mouse."""
        if self.isVisible():
            return self.pos()
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = area.center().x() - self.width() // 2
        y = area.top() + int((area.height() - self.height()) * VERTICAL_POSITION)
        return QPoint(x, max(area.top(), y))

    def _new_chat(self) -> None:
        self._pages.setCurrentIndex(0)
        self._session.new_chat()
        self._input.focus()

    def _show_history(self) -> None:
        self._history.refresh()
        self._pages.setCurrentIndex(1)

    def _open_conversation(self, conversation_id: str) -> None:
        self._pages.setCurrentIndex(0)
        self._session.open_conversation(conversation_id)

    def _poll_status(self) -> None:
        run_in_background(self._fetch_status, lambda result: self._show_status(*result), lambda _: None)

    def _fetch_status(self) -> tuple[IndexStatus, bool]:
        return self._api.index_status(), self._api.settings().is_cloud

    def _show_status(self, status: IndexStatus, is_cloud: bool) -> None:
        self._header.set_status(status)
        self._header.set_privacy(is_cloud)
