"""
The window the hotkey summons: a frameless, always-on-top night-sky panel with the sky header
and three pages, the conversation, chat history and Settings, that you move between without
leaving the window. Owns window behaviour (summon/dismiss animation, placement, page switching,
keyboard shortcuts, status polling) and composes the pieces.
"""

from __future__ import annotations

from PyQt6.QtCore import QAbstractAnimation, QPoint, Qt, QTimer
from PyQt6.QtGui import QCursor, QGuiApplication, QKeyEvent, QKeySequence, QPainter, QPaintEvent, QPixmap, QShortcut
from PyQt6.QtWidgets import (
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
from ui.chat.attachment_bar import AttachmentBar
from ui.chat.attachment_flow import AttachmentFlow
from ui.chat.chat_header import ChatHeader
from ui.chat.chat_input import ChatInput
from ui.chat.chat_session import ChatSession
from ui.chat.chat_stream import ChatStream
from ui.chat.chat_view import ChatView
from ui.chat.history_panel import HistoryPanel
from ui.chat.voice_input import VoiceInput
from ui.screen_capture import RegionCapture, save_capture
from ui.settings.settings_panel import SettingsPanel
from ui.theme.backdrop import NightBackdrop
from ui.theme.icons import app_icon
from ui.theme.motion import build_dismiss_animation, build_summon_animation, stop_animation
from ui.theme.soft_shadow import SoftShadow
from ui.theme.tokens import (
    CHAT_HEIGHT,
    CHAT_MIN_HEIGHT,
    CHAT_WIDTH,
    RADIUS_WINDOW,
    SHADOW_MARGIN,
)

STATUS_POLL_MS = 2000
# Long enough for the window's fade-out to leave the screen before it's photographed.
CAPTURE_DELAY_MS = 250
# Placing the window a little above center keeps it clear of the taskbar on short screens.
VERTICAL_POSITION = 0.42
FOOTER_TEXT = "Enter to send  ·  Shift+Enter for a new line  ·  Esc to hide"
CHAT_PAGE, HISTORY_PAGE, SETTINGS_PAGE = 0, 1, 2
PAGE_TITLES = {HISTORY_PAGE: "History", SETTINGS_PAGE: "Settings"}


class ChatWindow(QWidget):
    """The whole UI people see day to day."""

    def __init__(self, api: ApiClient) -> None:
        super().__init__()
        self._api = api
        self._animation: QAbstractAnimation | None = None
        self._status_timer = QTimer(self)
        self._header = ChatHeader()
        self._view = ChatView()
        self._history = HistoryPanel(api)
        self._settings = SettingsPanel(api)
        self._input = ChatInput()
        self._hint = QLabel(FOOTER_TEXT)
        self._pages = QStackedWidget()
        self._panel = NightBackdrop(self)
        self._shadow = SoftShadow(RADIUS_WINDOW)
        self._session = ChatSession(self._view, self._input, api, ChatStream())
        self._attachments = AttachmentBar()
        self._flow = AttachmentFlow(self._attachments, self._session)
        self._capture: RegionCapture | None = None
        self._voice = VoiceInput(self._input)

    def setup(self) -> None:
        """Builds the window and wires every signal."""
        self._configure_window()
        self._build_layout()
        self._session.connect_signals()
        self._session.status_received.connect(self._show_status)
        self._flow.connect_signals()
        self._voice.connect_signals()
        self._header.capture_clicked.connect(self.capture_screen)
        self._header.new_chat_clicked.connect(self._new_chat)
        self._header.history_clicked.connect(self.show_history)
        self._header.settings_clicked.connect(self.show_settings)
        self._header.back_clicked.connect(self.show_chat)
        self._header.minimize_clicked.connect(self.dismiss)
        self._header.close_clicked.connect(self.close_to_tray)
        self._history.opened.connect(self._open_conversation)
        self._settings.back_requested.connect(self.show_chat)
        # A save can switch between a local and a cloud model; refresh the header badge at once.
        self._settings.saved.connect(self._poll_status)
        self._status_timer.timeout.connect(self._poll_status)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._new_chat)
        QShortcut(QKeySequence("Ctrl+M"), self, activated=self._voice.listen)

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
        self._flow.offer_clipboard()
        self._status_timer.start(STATUS_POLL_MS)
        self._poll_status()

    def dismiss(self) -> None:
        """Glides away and hides; the conversation and current page are kept for next time."""
        if not self.isVisible():
            return
        self._status_timer.stop()
        stop_animation(self._animation)
        self._animation = build_dismiss_animation(self, self.pos())
        self._animation.finished.connect(self.hide)
        self._animation.start()

    def close_to_tray(self) -> None:
        """Hides like minimize, but reopens on the chat page; a running reply keeps going."""
        self.dismiss()
        self._go_to(CHAT_PAGE)

    def show_chat(self) -> None:
        self._go_to(CHAT_PAGE)
        self._input.focus()

    def show_history(self) -> None:
        self._history.refresh()
        self._go_to(HISTORY_PAGE)

    def show_settings(self) -> None:
        """Opens Settings inside this window; the header's back arrow returns to the chat."""
        self._settings.load()
        self._go_to(SETTINGS_PAGE)

    def ask_about_file(self, path: str) -> None:
        """File Explorer's "Ask Nimbus about this": a new chat with the file attached."""
        self.summon()
        self._new_chat()
        self._flow.attach_file(path)

    def capture_screen(self) -> None:
        """Hides the window, lets the user box part of the screen, and attaches that capture."""
        self.hide()
        QTimer.singleShot(CAPTURE_DELAY_MS, self._start_capture)

    def ask(self, text: str) -> None:
        """Summons the window and sends text straight away (used by tray shortcuts)."""
        self.summon()
        self.show_chat()
        self._session.send(text)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Esc steps back to the chat from a sub-page, and hides the window from the chat."""
        if event.key() == Qt.Key.Key_Escape:
            if self._pages.currentIndex() != CHAT_PAGE:
                self.show_chat()
            else:
                self.dismiss()
            return
        super().keyPressEvent(event)

    def _go_to(self, page: int) -> None:
        """Switches page and puts the matching header up. This translucent window doesn't
        reliably repaint on Windows after a layout shift or with graphics effects, so there are
        none, the footer hint keeps its space when hidden, and the window repaints each switch."""
        self._header.show_page(PAGE_TITLES.get(page))
        self._pages.setCurrentIndex(page)
        self._hint.setVisible(page == CHAT_PAGE)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        """The soft shadow in the transparent margin around the panel."""
        painter = QPainter(self)
        self._shadow.paint(painter, self.size(), self._panel.geometry())
        painter.end()

    def _start_capture(self) -> None:
        self._capture = RegionCapture()
        self._capture.captured.connect(self._attach_capture)
        self._capture.cancelled.connect(self.summon)
        self._capture.start()

    def _attach_capture(self, image: QPixmap) -> None:
        self._capture = None
        self.summon()
        self.show_chat()
        self._flow.attach_screenshot(save_capture(image))

    def _is_dismissing(self) -> bool:
        return (
            self.isVisible()
            and self.windowOpacity() < 1.0
            and self._animation is not None
            and (self._animation.state() == QAbstractAnimation.State.Running)
        )

    def _configure_window(self) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("Nimbus")
        self.setWindowIcon(app_icon())
        self.resize(CHAT_WIDTH + 2 * SHADOW_MARGIN, CHAT_HEIGHT + 2 * SHADOW_MARGIN)
        self.setMinimumHeight(CHAT_MIN_HEIGHT + 2 * SHADOW_MARGIN)

    def _build_layout(self) -> None:
        """The night panel (shadow painted by paintEvent): header, the pages, a slim footer."""
        panel = self._panel
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
        outer.addWidget(panel)
        self._pages.addWidget(self._chat_page())
        self._pages.addWidget(_padded(self._history))
        self._pages.addWidget(self._settings)
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._header)
        column.addWidget(self._pages, stretch=1)
        column.addLayout(self._footer(panel))

    def _chat_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 14, 20, 6)
        layout.setSpacing(12)
        layout.addWidget(self._view, stretch=1)
        layout.addWidget(self._attachments)
        layout.addWidget(self._input)
        return page

    def _footer(self, panel: QWidget) -> QHBoxLayout:
        self._hint.setObjectName("FooterHint")
        policy = self._hint.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self._hint.setSizePolicy(policy)
        row = QHBoxLayout()
        row.setContentsMargins(24, 0, 6, 6)
        row.addWidget(self._hint)
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
        self.show_chat()
        self._session.new_chat()

    def _open_conversation(self, conversation_id: str) -> None:
        self.show_chat()
        self._session.open_conversation(conversation_id)

    def _poll_status(self) -> None:
        run_in_background(self._fetch_status, lambda result: self._show_status(*result), lambda _: None)

    def _fetch_status(self) -> tuple[IndexStatus, bool]:
        return self._api.index_status(), self._api.settings().is_cloud

    def _show_status(self, status: IndexStatus, is_cloud: bool) -> None:
        self._header.set_status(status)
        self._header.set_privacy(is_cloud)


def _padded(widget: QWidget) -> QWidget:
    """Wraps a page in the same side margins as the chat page."""
    holder = QWidget()
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(20, 14, 20, 6)
    layout.addWidget(widget)
    return holder
