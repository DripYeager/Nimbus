"""
Registers the configured global hotkey and emits summoned() when it fires, debounced against
rapid re-triggers. Owns the keypress -> summon mapping only — it doesn't know what summoning does.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import QObject, pyqtSignal
from pynput import keyboard

from core.exceptions import HotkeyError
from core.logger import get_logger

logger = get_logger(__name__)

DEBOUNCE_SECONDS = 0.5


class HotkeyListener(QObject):
    """Listens for one global hotkey and emits summoned() when it fires, debounced."""

    summoned = pyqtSignal()

    def __init__(self, hotkey: str) -> None:
        super().__init__()
        self._hotkey = hotkey
        self._listener: keyboard.GlobalHotKeys | None = None
        self._last_trigger = 0.0

    def start(self) -> None:
        """Starts listening for the hotkey on a background thread."""
        try:
            self._listener = keyboard.GlobalHotKeys({self._hotkey: self._on_activate})
            self._listener.start()
        except ValueError as e:
            raise HotkeyError(f"Invalid hotkey '{self._hotkey}': {e}") from e
        logger.info("Hotkey listener started", extra={"hotkey": self._hotkey})

    def stop(self) -> None:
        """Stops listening. Safe to call even if start() was never called."""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
            logger.info("Hotkey listener stopped", extra={"hotkey": self._hotkey})

    def _on_activate(self) -> None:
        """Runs on pynput's listener thread — emits summoned() unless it fired too recently."""
        now = time.monotonic()
        if now - self._last_trigger < DEBOUNCE_SECONDS:
            return
        self._last_trigger = now
        self.summoned.emit()
