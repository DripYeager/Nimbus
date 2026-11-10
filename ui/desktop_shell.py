"""
Everything the user interacts with, wired together: the chat window, the tray icon, the global
hotkey, the in-window Settings page and first-run onboarding. Reacts to settings changes (a new
hotkey) and second launches. Owns UI composition; the engine and process lifecycle belong to
core/app_runtime.py.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QObject, pyqtSignal

from config.settings import get_settings
from core.exceptions import HotkeyError
from core.logger import get_logger
from ui.api_client import ApiClient
from ui.chat.chat_window import ChatWindow
from ui.hotkey import HotkeyListener
from ui.onboarding.onboarding_wizard import OnboardingWizard
from ui.single_instance import InstanceServer
from ui.tray import TrayIcon

logger = get_logger(__name__)


class DesktopShell(QObject):
    """Builds and shows the UI. settings_changed may be emitted from any thread; the slot
    runs on the GUI thread."""

    settings_changed = pyqtSignal()

    def __init__(self, api: ApiClient, on_quit: Callable[[], None]) -> None:
        super().__init__()
        self._api = api
        self._on_quit = on_quit
        self._chat = ChatWindow(api)
        self._tray = TrayIcon(api)
        self._hotkey = HotkeyListener(get_settings().hotkey)
        self._instances = InstanceServer()
        self._wizard: OnboardingWizard | None = None

    def start(self) -> None:
        """Shows the tray, registers the hotkey, and runs onboarding on first launch."""
        self._chat.setup()
        self._tray.setup()
        self._tray.summon_requested.connect(self._chat.summon)
        self._tray.settings_requested.connect(self.open_settings)
        self._tray.quit_requested.connect(self._on_quit)
        self._hotkey.summoned.connect(self._chat.toggle)
        self._instances.summon_requested.connect(self._chat.summon)
        self._instances.listen()
        self.settings_changed.connect(self._apply_hotkey)
        hotkey_ready = self._register_hotkey()
        if not get_settings().onboarding_complete:
            self._run_onboarding()
        elif hotkey_ready:
            # Only one tray balloon shows at a time; a clash warning must not be replaced by this.
            self._tray.notify(f"Nimbus is ready. Press {_readable(get_settings().hotkey)} to summon me.")

    def stop(self) -> None:
        self._hotkey.stop()
        self._tray.hide()
        self._chat.hide()

    def open_settings(self) -> None:
        """Summons the chat window on its Settings page."""
        self._chat.summon()
        self._chat.show_settings()

    def _run_onboarding(self) -> None:
        self._wizard = OnboardingWizard(self._api)
        self._wizard.completed.connect(self._finish_onboarding)
        self._wizard.show()

    def _finish_onboarding(self) -> None:
        self._wizard = None
        self._chat.summon()

    def _register_hotkey(self) -> bool:
        """Registers the hotkey; a clash becomes a tray message rather than a crash. Returns
        whether it worked."""
        try:
            self._hotkey.start()
        except HotkeyError as e:
            logger.warning("Hotkey unavailable", extra={"error": str(e)})
            self._tray.notify(f"{e} You can still open Nimbus from the tray icon.")
            return False
        return True

    def _apply_hotkey(self) -> None:
        """Re-registers the hotkey if the user changed it in Settings."""
        wanted = get_settings().hotkey
        if wanted == self._hotkey.hotkey:
            return
        try:
            self._hotkey.rebind(wanted)
            self._tray.notify(f"Hotkey changed to {_readable(wanted)}.")
        except HotkeyError as e:
            self._tray.notify(str(e))


def _readable(hotkey: str) -> str:
    """ "<ctrl>+<space>" → "Ctrl+Space" for messages."""
    return "+".join(part.strip("<>").capitalize() for part in hotkey.split("+"))
