"""
A label whose text carries a soft coloured halo, painted by hand. It replaces Qt's drop-shadow
effect, which makes a translucent window re-render whole regions offscreen and, on Windows,
can leave parts of it stale after a change. Painting only; the text and font come from QLabel.
"""

from __future__ import annotations

from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import QLabel, QWidget

# Rings of offset copies under the text; each is faint, and together they read as a glow.
HALO_OFFSETS = ((-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, -1), (-1, 1), (1, 1), (0, 3), (-2, 2), (2, 2))
HALO_MARGIN_PX = 3


class GlowLabel(QLabel):
    """A QLabel with a halo of glow_color around its text."""

    def __init__(self, text: str, glow_color: QColor, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._glow_color = glow_color
        # Room for the halo, so its edges aren't cut off by the label's own bounds.
        self.setContentsMargins(HALO_MARGIN_PX, HALO_MARGIN_PX, HALO_MARGIN_PX, HALO_MARGIN_PX)

    def glow_color(self) -> QColor:
        return QColor(self._glow_color)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self.font())
        painter.setPen(self._glow_color)
        rect = self.contentsRect()
        for dx, dy in HALO_OFFSETS:
            painter.drawText(rect.translated(dx, dy), self.alignment(), self.text())
        painter.end()
        super().paintEvent(event)
