"""
The two hand-drawn widgets behind the overlay's look: the rounded translucent card frame and
the bobbing gold cloud glyph. Pure painting — neither widget owns layout, animation timing, or
window-level state; overlay.py drives when the glyph bobs and where the card sits.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget

from ui.overlay_theme import ACCENT_GOLD, BACKGROUND_RGBA, BORDER_RGBA, CARD_RADIUS, GLYPH_SIZE


class CloudGlyph(QWidget):
    """A small code-drawn cloud that bobs while Nimbus is thinking; frozen otherwise."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(GLYPH_SIZE, GLYPH_SIZE)
        self._offset_y = 0.0

    def set_offset_y(self, offset: float) -> None:
        """Moves the glyph vertically for the bob animation, then repaints it."""
        self._offset_y = offset
        self.update()

    def paintEvent(self, event: object) -> None:
        """Draws a small flat gold cloud as three overlapping circles plus a base."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(0, self._offset_y)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ACCENT_GOLD))
        painter.drawEllipse(2, 8, 8, 8)
        painter.drawEllipse(7, 4, 9, 9)
        painter.drawEllipse(13, 8, 7, 7)
        painter.drawRoundedRect(2, 11, 16, 6, 3, 3)


class OverlayCard(QWidget):
    """Paints the rounded, translucent card background and border; a plain container otherwise."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

    def paintEvent(self, event: object) -> None:
        """Fills a rounded rect in the background token, stroked with the border token."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(QColor(*BORDER_RGBA))
        painter.setBrush(QColor(*BACKGROUND_RGBA))
        painter.drawRoundedRect(rect, CARD_RADIUS, CARD_RADIUS)
