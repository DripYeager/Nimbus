"""
The live "working on it" line under a reply that hasn't started yet: a gold shimmer sweeping
across a rotating phrase, animated dots, and a seconds counter once the wait gets long, so a
slow local model never looks frozen. Display only; it knows nothing about the request.
"""

from __future__ import annotations

import html
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLabel, QWidget

from ui.theme.tokens import CLOUD_GOLD, CLOUD_GOLD_DEEP, TEXT

PHRASES = ("Charging up", "Riding the cloud", "Searching your files", "Thinking it through", "Gathering energy")
TICK_MS = 90
TICKS_PER_DOT = 4
DOT_FRAMES = ("", ".", "..", "...")
TICKS_PER_PHRASE = 36
SHIMMER_WIDTH = 3
# The shimmer runs a few characters past the end so each sweep has a short pause.
SHIMMER_TAIL = 6
SHOW_ELAPSED_AFTER_SECONDS = 5


class ThinkingIndicator(QLabel):
    """Starts animating on start(), freezes and hides on stop()."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Thinking")
        self.setTextFormat(Qt.TextFormat.RichText)
        self._ticks = 0
        self._started = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._advance)
        self.hide()

    def start(self) -> None:
        self._ticks = 0
        self._started = time.monotonic()
        self._render()
        self.show()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def is_animating(self) -> bool:
        return self._timer.isActive()

    def phrase(self) -> str:
        return PHRASES[(self._ticks // TICKS_PER_PHRASE) % len(PHRASES)]

    def _advance(self) -> None:
        self._ticks += 1
        self._render()

    def _render(self) -> None:
        dots = DOT_FRAMES[(self._ticks // TICKS_PER_DOT) % len(DOT_FRAMES)]
        # Dots get a fixed-width slot so the counter doesn't wobble as they change.
        padded_dots = dots + "&nbsp;" * (len(DOT_FRAMES[-1]) - len(dots))
        counter = _counter(int(time.monotonic() - self._started))
        self.setText(f"{_shimmer(self.phrase(), self._ticks)}{padded_dots}{counter}")


def _counter(elapsed_seconds: int) -> str:
    """ "12s" after a long-ish wait, so a slow model visibly keeps going; nothing before that."""
    if elapsed_seconds < SHOW_ELAPSED_AFTER_SECONDS:
        return ""
    return f"&nbsp;&nbsp;<span style='color:{CLOUD_GOLD_DEEP}'>{elapsed_seconds}s</span>"


def _shimmer(text: str, tick: int) -> str:
    """The phrase in gold, with a bright band a few characters wide moving left to right."""
    position = tick % (len(text) + SHIMMER_TAIL)
    parts = []
    for index, char in enumerate(text):
        color = TEXT if 0 <= position - index < SHIMMER_WIDTH else CLOUD_GOLD
        parts.append(f"<span style='color:{color}'>{html.escape(char)}</span>")
    return "".join(parts)
