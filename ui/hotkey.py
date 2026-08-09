"""
Registers the configured global hotkey and emits summoned() when it fires, debounced against
rapid re-triggers. Owns the keypress -> summon mapping only — it doesn't know what summoning does.

pynput's GlobalHotKeys tracks which of a combo's keys are held in its own internal state, and
only clears a key once it sees that key's release event. If a modifier's key-up is ever missed
by the OS — which happens reliably here, since a successful activation immediately steals
keyboard focus away from whatever had it — the modifier stays stuck "held" in that internal
state forever, and the rest of the combo alone re-triggers it from then on. On Windows,
_on_activate re-verifies every key in the combo against the live OS key state before firing,
since that's immune to pynput's own stale bookkeeping.
"""

from __future__ import annotations

import ctypes
import sys
import time

from PyQt6.QtCore import QObject, pyqtSignal
from pynput import keyboard
from pynput.keyboard import HotKey, Key, KeyCode

from core.exceptions import HotkeyError
from core.logger import get_logger

logger = get_logger(__name__)

DEBOUNCE_SECONDS = 0.5
STOP_JOIN_TIMEOUT_SECONDS = 2.0
KEY_DOWN_FLAG = 0x8000
IS_WINDOWS = sys.platform == "win32"


class HotkeyListener(QObject):
    """Listens for one global hotkey and emits summoned() when it fires, debounced."""

    summoned = pyqtSignal()

    def __init__(self, hotkey: str) -> None:
        super().__init__()
        self._hotkey = hotkey
        self._listener: keyboard.GlobalHotKeys | None = None
        self._combo_vks: list[int] = []
        self._last_trigger = 0.0

    def start(self) -> None:
        """Starts listening for the hotkey on a background thread."""
        try:
            if IS_WINDOWS:
                self._combo_vks = [_vk_of(key) for key in HotKey.parse(self._hotkey)]
            self._listener = keyboard.GlobalHotKeys({self._hotkey: self._on_activate})
            self._listener.start()
        except ValueError as e:
            raise HotkeyError(f"Invalid hotkey '{self._hotkey}': {e}") from e
        logger.info("Hotkey listener started", extra={"hotkey": self._hotkey})

    def stop(self) -> None:
        """Stops listening and waits for the background thread to actually exit. Safe to call
        even if start() was never called."""
        if self._listener is not None:
            self._listener.stop()
            self._listener.join(timeout=STOP_JOIN_TIMEOUT_SECONDS)
            self._listener = None
            logger.info("Hotkey listener stopped", extra={"hotkey": self._hotkey})

    def _on_activate(self) -> None:
        """Runs on pynput's listener thread — emits summoned() unless it fired too recently, or
        the combo isn't actually fully held right now (a stuck-modifier false trigger)."""
        if IS_WINDOWS and not _combo_actually_held(self._combo_vks):
            logger.info("Ignoring a stale hotkey activation", extra={"hotkey": self._hotkey})
            return
        now = time.monotonic()
        if now - self._last_trigger < DEBOUNCE_SECONDS:
            return
        self._last_trigger = now
        self.summoned.emit()


def _vk_of(key: Key | KeyCode) -> int:
    """Resolves the Windows virtual-key code for one parsed hotkey combo part."""
    if isinstance(key, Key):
        return key.value.vk
    if key.vk is not None:
        return key.vk
    return ctypes.windll.user32.VkKeyScanW(ord(key.char)) & 0xFF


def _combo_actually_held(vks: list[int]) -> bool:
    """True if every one of vks is physically held right now, per a live OS query — immune to
    pynput's own internal state, which is exactly what gets stuck after a missed key-up."""
    return all(ctypes.windll.user32.GetAsyncKeyState(vk) & KEY_DOWN_FLAG for vk in vks)
