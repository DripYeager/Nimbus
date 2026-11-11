"""
A soft drop shadow for a rounded panel, painted from a cached image. It replaces Qt's
drop-shadow effect on the chat window's panel: that effect re-renders the whole panel and its
blur on every small update, which made the window slow to draw and, on Windows, left the header
stale after switching pages. Painting only.
"""

from __future__ import annotations

from PyQt6.QtCore import QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QImage, QPainter

SHADOW_LAYERS = 24
# Each layer is nearly invisible; where they stack up near the panel they add up to a shadow.
SHADOW_LAYER_ALPHA = 9
SHADOW_DROP_PX = 10


class SoftShadow:
    """Draws the shadow for one panel rectangle, rebuilding its image only when sizes change."""

    def __init__(self, radius: float) -> None:
        self._radius = radius
        self._image: QImage | None = None
        self._key: tuple[QSize, QRect] | None = None

    def paint(self, painter: QPainter, canvas: QSize, panel: QRect) -> None:
        if self._key != (canvas, panel) or self._image is None:
            self._image = _shadow_image(canvas, panel, self._radius)
            self._key = (QSize(canvas), QRect(panel))
        painter.drawImage(0, 0, self._image)


def _shadow_image(canvas: QSize, panel: QRect, radius: float) -> QImage:
    """Layered rounded rectangles that spread out from the panel and fade."""
    image = QImage(canvas, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(0, 0, 0, SHADOW_LAYER_ALPHA))
    base = QRectF(panel).translated(0, SHADOW_DROP_PX)
    for spread in range(SHADOW_LAYERS):
        rect = base.adjusted(-spread, -spread, spread, spread)
        painter.drawRoundedRect(rect, radius + spread, radius + spread)
    painter.end()
    return image
