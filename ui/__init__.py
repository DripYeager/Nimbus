"""Everything the user sees: the chat window, Settings, onboarding, the tray icon and the hotkey."""

from __future__ import annotations

from ui.api_client import ApiClient
from ui.chat.chat_window import ChatWindow
from ui.desktop_shell import DesktopShell
from ui.hotkey import HotkeyListener
from ui.tray import TrayIcon

__all__ = ["ApiClient", "ChatWindow", "DesktopShell", "HotkeyListener", "TrayIcon"]
