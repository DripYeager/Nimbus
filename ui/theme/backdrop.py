"""
The chat window's body: a rounded night-sky panel lit by two soft glows, gi orange rising from
the bottom-left and wristband blue from the top-right, with a few faint stars. Pure painting;
it hosts whatever layout is put inside it.
"""

from __future__ import annotations

import random

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPaintEvent, QPen, QRadialGradient
from PyQt6.QtWidgets import QFrame, QWidget

from ui.theme.tokens import BORDER_STRONG, GI_BLUE, GI_ORANGE, NIGHT, RADIUS_WINDOW

STAR_COUNT = 28
# Fixed seed so the stars don't jump around between repaints or launches.
STAR_SEED = 7
GLOW_STRENGTH = 0.16


class NightBackdrop(QFrame):
    """A rounded night panel; children sit on top of the painted sky."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("NightBackdrop")
        rng = random.Random(STAR_SEED)
        self._stars = [(rng.random(), rng.random() * 0.6, rng.uniform(0.6, 1.6)) for _ in range(STAR_COUNT)]

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        shape = QPainterPath()
        shape.addRoundedRect(rect, RADIUS_WINDOW, RADIUS_WINDOW)
        painter.setClipPath(shape)
        painter.fillRect(rect, QColor(NIGHT))
        _glow(painter, QPointF(rect.left(), rect.bottom()), rect.width() * 0.8, GI_ORANGE)
        _glow(painter, QPointF(rect.right(), rect.top()), rect.width() * 0.7, GI_BLUE)
        self._paint_stars(painter, rect)
        painter.setClipping(False)
        painter.setPen(QPen(QColor(BORDER_STRONG), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(shape)

    def _paint_stars(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        for x, y, radius in self._stars:
            painter.setBrush(QColor(255, 255, 255, int(40 + 50 * (radius - 0.6))))
            painter.drawEllipse(QPointF(rect.left() + x * rect.width(), rect.top() + y * rect.height()), radius, radius)


def _glow(painter: QPainter, center: QPointF, radius: float, hex_color: str) -> None:
    """One soft radial light."""
    gradient = QRadialGradient(center, radius)
    inner = QColor(hex_color)
    inner.setAlphaF(GLOW_STRENGTH)
    outer = QColor(hex_color)
    outer.setAlphaF(0.0)
    gradient.setColorAt(0.0, inner)
    gradient.setColorAt(1.0, outer)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawEllipse(center, radius, radius)
