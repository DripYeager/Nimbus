"""
Registers the summon hotkey with Windows (RegisterHotKey) and emits summoned() when it fires.
Unlike a keyboard hook, a registered hotkey needs no admin rights, never sees other keystrokes,
and can't get confused by a missed key-up. Owns the hotkey -> signal mapping only.
"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes

from PyQt6.QtCore import QObject, pyqtSignal

from core.exceptions import HotkeyError
from core.logger import get_logger

logger = get_logger(__name__)

MODIFIERS = {"<ctrl>": 0x0002, "<alt>": 0x0001, "<shift>": 0x0004, "<win>": 0x0008, "<cmd>": 0x0008}
NAMED_KEYS = {"<space>": 0x20, "<tab>": 0x09, "<enter>": 0x0D, "<esc>": 0x1B, "<backspace>": 0x08}
F1_VK = 0x70
MAX_FUNCTION_KEY = 24
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_ID = 0x4E42
REGISTER_WAIT_SECONDS = 2.0
DEBOUNCE_SECONDS = 0.4


def parse_hotkey(hotkey: str) -> tuple[int, int]:
    """Turns "<ctrl>+<shift>+n" into (modifier flags, virtual-key code).

    Raises:
        HotkeyError: if there's no modifier, no key, more than one key, or an unknown key.
    """
    modifiers, keys = 0, []
    for part in (p.strip().lower() for p in hotkey.split("+") if p.strip()):
        if part in MODIFIERS:
            modifiers |= MODIFIERS[part]
        else:
            keys.append(part)
    if modifiers == 0 or len(keys) != 1:
        raise HotkeyError(f"'{hotkey}' needs at least one modifier (Ctrl, Alt, Shift, Win) plus exactly one key.")
    return modifiers, _virtual_key(keys[0], hotkey)


def _virtual_key(key: str, hotkey: str) -> int:
    """The Windows virtual-key code for one key name."""
    if key in NAMED_KEYS:
        return NAMED_KEYS[key]
    if key.startswith("<f") and key.endswith(">") and key[2:-1].isdigit() and 1 <= int(key[2:-1]) <= MAX_FUNCTION_KEY:
        return F1_VK + int(key[2:-1]) - 1
    if len(key) == 1 and key.isascii() and key.isalnum():
        return ord(key.upper())
    if len(key) == 1 and sys.platform == "win32":
        # VkKeyScanW answers -1 (a SHORT) for a character the current keyboard layout can't type.
        code = ctypes.windll.user32.VkKeyScanW(ord(key)) & 0xFFFF
        if code != 0xFFFF:
            return code & 0xFF
    raise HotkeyError(f"Unknown key '{key}' in hotkey '{hotkey}'.")


class HotkeyListener(QObject):
    """Owns one registered hotkey on a dedicated message-loop thread."""

    summoned = pyqtSignal()

    def __init__(self, hotkey: str) -> None:
        super().__init__()
        self._hotkey = hotkey
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._registered = threading.Event()
        self._error: str | None = None
        self._last_fired = 0.0

    @property
    def hotkey(self) -> str:
        return self._hotkey

    def start(self) -> None:
        """Registers the hotkey, raising HotkeyError if it's invalid or already taken."""
        if sys.platform != "win32":
            raise HotkeyError("The global hotkey is only supported on Windows.")
        modifiers, vk = parse_hotkey(self._hotkey)
        self._registered.clear()
        self._error = None
        self._thread = threading.Thread(target=self._run, args=(modifiers, vk), name="hotkey", daemon=True)
        self._thread.start()
        if not self._registered.wait(REGISTER_WAIT_SECONDS) or self._error:
            self.stop()
            raise HotkeyError(self._error or f"Timed out registering '{self._hotkey}'.")
        logger.info("Hotkey registered", extra={"hotkey": self._hotkey})

    def stop(self) -> None:
        """Unregisters the hotkey and ends its thread. Safe to call more than once."""
        if self._thread is None:
            return
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread.join(timeout=REGISTER_WAIT_SECONDS)
        self._thread = None
        self._thread_id = 0

    def rebind(self, hotkey: str) -> None:
        """Switches to a new hotkey, restoring the old one if the new one can't be registered."""
        previous = self._hotkey
        self.stop()
        self._hotkey = hotkey
        try:
            self.start()
        except HotkeyError:
            self._hotkey = previous
            # Restoring can fail too (the old combo got taken meanwhile); the new hotkey's error
            # is still the one worth reporting.
            try:
                self.start()
            except HotkeyError:
                logger.warning("Couldn't restore the previous hotkey", extra={"hotkey": previous})
            raise

    def _run(self, modifiers: int, vk: int) -> None:
        """Registers on this thread (hotkey messages go to the registering thread) and pumps
        messages until WM_QUIT."""
        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, HOTKEY_ID, modifiers | MOD_NOREPEAT, vk):
            self._error = f"'{self._hotkey}' is already used by another app. Pick a different one in Settings."
            self._registered.set()
            return
        self._registered.set()
        message = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == WM_HOTKEY:
                    self._fire()
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)

    def _fire(self) -> None:
        """Emits summoned(), ignoring a second press within the debounce window."""
        now = time.monotonic()
        if now - self._last_fired >= DEBOUNCE_SECONDS:
            self._last_fired = now
            self.summoned.emit()
