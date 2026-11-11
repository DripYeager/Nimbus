"""
A small live audio meter: five rounded bars that rise with the microphone's loudness, shown
beside the mic button while it records so the user can see they're being heard. Quiet sounds
are boosted (a square-root curve) so normal speech fills most of the meter. Painting only.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import QSizePolicy, QWidget

from ui.theme.tokens import BORDER_STRONG, GI_ORANGE

BAR_COUNT = 5
BAR_WIDTH = 3
BAR_GAP = 3
METER_HEIGHT = 18
# Loudness (RMS) at which the meter is full. Measured on a laptop microphone array: room noise
# sits near 0.001 and speech around 0.01 to 0.03, so speech fills about half to three-quarters.
FULL_SCALE = 0.05
# Below this fill the bars stay grey, so room hiss doesn't look like speech.
ACTIVE_FILL = 0.25
# Each update keeps this much of the previous level, so the bars fall smoothly instead of flickering.
DECAY = 0.6
# The middle bars stand tallest, like a voice waveform.
BAR_SHAPE = (0.55, 0.8, 1.0, 0.8, 0.55)


class LevelMeter(QWidget):
    """Call set_level() with each chunk's loudness; reset() when recording stops."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._level = 0.0
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setToolTip("Microphone level")

    def sizeHint(self) -> QSize:
        return QSize(BAR_COUNT * BAR_WIDTH + (BAR_COUNT - 1) * BAR_GAP, METER_HEIGHT)

    def level(self) -> float:
        """The shown level, 0 (silent) to 1 (full)."""
        return self._level

    def set_level(self, loudness: float) -> None:
        target = min(1.0, max(0.0, loudness / FULL_SCALE)) ** 0.5
        # Rises at once, falls gradually.
        self._level = target if target > self._level else self._level * DECAY + target * (1 - DECAY)
        self.update()

    def reset(self) -> None:
        self._level = 0.0
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        height = self.height()
        for index, shape in enumerate(BAR_SHAPE):
            bar = max(BAR_WIDTH, height * shape * self._level)
            x = index * (BAR_WIDTH + BAR_GAP)
            painter.setBrush(QColor(GI_ORANGE if self._level >= ACTIVE_FILL else BORDER_STRONG))
            painter.drawRoundedRect(QRectF(x, (height - bar) / 2, BAR_WIDTH, bar), 1.5, 1.5)
        painter.end()
