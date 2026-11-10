"""
The system tray icon and its menu: open the chat, see indexing progress, pause/resume,
rebuild, open Settings, quit. Built on Qt's own tray support so the whole UI runs on one
toolkit and one thread. Owns tray UI only; it asks the API for status and emits signals for
everything else.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from core.logger import get_logger
from models.schema import IndexStatus
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.status_text import describe_status
from ui.theme.icons import app_icon
from ui.theme.line_icons import line_icon
from ui.theme.tokens import CLOUD_GOLD

logger = get_logger(__name__)

STATUS_REFRESH_MS = 3000
MENU_ICON_SIZE = 16
NOTIFICATION_MS = 4000
TOOLTIP_TITLE = "Nimbus"


class TrayIcon(QObject):
    """The tray icon. Emits signals; the runtime decides what they do."""

    summon_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    capture_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, api: ApiClient) -> None:
        super().__init__()
        self._api = api
        self._tray: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None
        self._status_action: QAction | None = None
        self._pause_action: QAction | None = None
        self._is_paused = False
        self._timer: QTimer | None = None

    def setup(self) -> None:
        """Builds the icon and menu, shows it, and starts polling for status."""
        self._tray = QSystemTrayIcon(app_icon(), self)
        self._tray.setToolTip(TOOLTIP_TITLE)
        self._tray.setContextMenu(self._build_menu())
        self._tray.activated.connect(self._handle_activated)
        self._tray.show()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh_status)
        self._timer.start(STATUS_REFRESH_MS)
        self.refresh_status()

    def notify(self, message: str) -> None:
        """Shows a balloon notification."""
        if self._tray is not None:
            self._tray.showMessage(TOOLTIP_TITLE, message, app_icon(), NOTIFICATION_MS)

    def hide(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        if self._tray is not None:
            self._tray.hide()

    def refresh_status(self) -> None:
        run_in_background(self._api.index_status, self._show_status, lambda _: None)

    def _build_menu(self) -> QMenu:
        """Open, status line, pause/resume, rebuild, settings, quit."""
        menu = QMenu()
        menu.addAction(_menu_icon("cloud"), "Open Nimbus", self.summon_requested.emit)
        menu.addAction(_menu_icon("scan"), "Ask about something on screen", self.capture_requested.emit)
        menu.addSeparator()
        self._status_action = menu.addAction(_menu_icon("zap"), "Checking index…")
        self._status_action.setEnabled(False)
        self._pause_action = menu.addAction(_menu_icon("pause"), "Pause indexing", self._toggle_pause)
        menu.addAction(_menu_icon("refresh-cw"), "Rebuild index", self._rebuild)
        menu.addAction(_menu_icon("settings"), "Settings…", self.settings_requested.emit)
        menu.addSeparator()
        menu.addAction(_menu_icon("x"), "Quit Nimbus", self.quit_requested.emit)
        self._menu = menu
        return menu

    def _show_status(self, status: IndexStatus) -> None:
        """Updates the tooltip, the menu's status line and the pause item's label."""
        text = describe_status(status)
        self._tray.setToolTip(f"{TOOLTIP_TITLE}: {text}")
        self._status_action.setText(text)
        self._is_paused = status.is_paused
        self._pause_action.setText("Resume indexing" if status.is_paused else "Pause indexing")
        self._pause_action.setIcon(_menu_icon("play" if status.is_paused else "pause"))

    def _toggle_pause(self) -> None:
        run_in_background(lambda: self._api.set_paused(not self._is_paused), self._show_status, self.notify)

    def _rebuild(self) -> None:
        def _started(status: IndexStatus) -> None:
            self.notify("Re-reading all your files in the background.")
            self._show_status(status)

        run_in_background(self._api.rebuild_index, _started, self.notify)

    def _handle_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """A left click (or double click) on the icon opens the chat."""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.summon_requested.emit()


def _menu_icon(name: str) -> QIcon:
    return line_icon(name, CLOUD_GOLD, MENU_ICON_SIZE)
