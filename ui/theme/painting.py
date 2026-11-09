"""
Code-drawn artwork: the golden cloud (logo, tray icon, thinking glyph), the sky header with
its speed-line streaks, the glowing aura around the input, and the power-level meter. Pure
painting — none of these widgets owns layout or decides when it animates.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtProperty
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPaintEvent, QPen
from PyQt6.QtWidgets import QFrame, QWidget

from ui.theme.tokens import (
    BORDER,
    CLOUD_GOLD,
    CLOUD_GOLD_DEEP,
    CLOUD_SHADOW,
    ENERGY_ORANGE,
    RADIUS_WINDOW,
    SKY_BOTTOM,
    SKY_TOP,
    SURFACE,
)

# Puffs as (x, y, width, height) in a 100x60 design box: round lumps over a wide, flat belly.
_PUFFS = ((4, 24, 34, 34), (20, 10, 38, 38), (42, 2, 40, 40), (64, 12, 32, 32), (72, 26, 26, 26), (14, 30, 72, 26))
STREAK_MAX_ALPHA = 110
SHADOW_DEPTH = 0.06
_STREAKS = ((0.12, 0.30, 0.22), (0.55, 0.22, 0.30), (0.30, 0.62, 0.18), (0.72, 0.70, 0.24), (0.86, 0.40, 0.12))


def cloud_path(rect: QRectF, with_tail: bool = True) -> QPainterPath:
    """A cloud fitted into rect, optionally trailing a swept tail to the right — the 'just
    arrived at speed' silhouette that gives the logo its motion."""
    body_width = rect.width() * (0.78 if with_tail else 1.0)
    scale_x, scale_y = body_width / 100.0, rect.height() / 60.0
    path = QPainterPath()
    for x, y, width, height in _PUFFS:
        puff = QPainterPath()
        puff.addEllipse(QRectF(rect.x() + x * scale_x, rect.y() + y * scale_y, width * scale_x, height * scale_y))
        path = path.united(puff)
    if with_tail:
        path = path.united(_tail_path(rect, body_width))
    return path.simplified()


def _tail_path(rect: QRectF, body_width: float) -> QPainterPath:
    """A tapering swoosh leaving the cloud's right side."""
    start_x, mid_y = rect.x() + body_width * 0.86, rect.y() + rect.height() * 0.62
    end = QPointF(rect.right(), rect.y() + rect.height() * 0.42)
    tail = QPainterPath(QPointF(start_x, mid_y - rect.height() * 0.14))
    tail.quadTo(QPointF(start_x + (end.x() - start_x) * 0.6, mid_y + rect.height() * 0.02), end)
    back_control = QPointF(start_x + (end.x() - start_x) * 0.5, mid_y + rect.height() * 0.2)
    tail.quadTo(back_control, QPointF(start_x, mid_y + rect.height() * 0.14))
    tail.closeSubpath()
    return tail


def paint_cloud(painter: QPainter, rect: QRectF, with_tail: bool = True) -> None:
    """Paints a shaded golden cloud: a deeper-gold underside offset below a bright body."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    # The underside is drawn below the body, so the body shrinks to keep both inside rect.
    shadow_offset = rect.height() * SHADOW_DEPTH
    rect = rect.adjusted(0, 0, 0, -shadow_offset)
    shadow_rect = rect.translated(0, shadow_offset)
    painter.setBrush(QColor(CLOUD_SHADOW))
    painter.drawPath(cloud_path(shadow_rect, with_tail))
    gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    gradient.setColorAt(0.0, QColor("#FFE38A"))
    gradient.setColorAt(0.55, QColor(CLOUD_GOLD))
    gradient.setColorAt(1.0, QColor(CLOUD_GOLD_DEEP))
    painter.setBrush(gradient)
    painter.drawPath(cloud_path(rect, with_tail))
    painter.restore()


class CloudGlyph(QWidget):
    """A small cloud that bobs while Nimbus is thinking."""

    def __init__(self, size: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._offset_y = 0.0

    def set_offset_y(self, offset: float) -> None:
        self._offset_y = offset
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        margin = self.width() * 0.1
        rect = QRectF(margin, self.height() * 0.25 + self._offset_y, self.width() - 2 * margin, self.height() * 0.5)
        paint_cloud(painter, rect, with_tail=False)


class SkyHeader(QWidget):
    """The window's header: a sky gradient with rounded top corners and drifting speed-line
    streaks. streak_phase (0..1) is animated briefly when the window is summoned."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._streak_phase = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def _get_streak_phase(self) -> float:
        return self._streak_phase

    def _set_streak_phase(self, value: float) -> None:
        self._streak_phase = value
        self.update()

    streak_phase = pyqtProperty(float, fget=_get_streak_phase, fset=_set_streak_phase)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Sky gradient first, then semi-transparent white streaks shifted by the phase."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, QColor(SKY_TOP))
        gradient.setColorAt(1.0, QColor(SKY_BOTTOM))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(_top_rounded_rect(QRectF(self.rect()), RADIUS_WINDOW))
        # Streaks only show mid-sweep, so the header is calm at rest.
        alpha = int(STREAK_MAX_ALPHA * math.sin(math.pi * self._streak_phase))
        if alpha <= 0:
            return
        painter.setPen(QPen(QColor(255, 255, 255, alpha), 2, cap=Qt.PenCapStyle.RoundCap))
        for x, y, length in _STREAKS:
            shift = (x - self._streak_phase * 0.6) % 1.0
            start = QPointF(shift * self.width(), y * self.height())
            painter.drawLine(start, QPointF(start.x() + length * self.width() * 0.4, start.y()))


class AuraFrame(QFrame):
    """A rounded frame whose border glows gold-to-orange; glow (0..1) is animated while the
    assistant is thinking and rests at 0 otherwise."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._glow = 0.0

    def _get_glow(self) -> float:
        return self._glow

    def _set_glow(self, value: float) -> None:
        self._glow = value
        self.update()

    glow = pyqtProperty(float, fget=_get_glow, fset=_set_glow)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        if self._glow > 0:
            gradient = QLinearGradient(rect.topLeft(), rect.topRight())
            gradient.setColorAt(0.0, _with_alpha(CLOUD_GOLD, self._glow))
            gradient.setColorAt(1.0, _with_alpha(ENERGY_ORANGE, self._glow))
            painter.setPen(QPen(gradient, 2 + 2 * self._glow))
        else:
            painter.setPen(QPen(QColor(BORDER), 1))
        painter.setBrush(QColor(SURFACE))
        painter.drawRoundedRect(rect, 16, 16)


class PowerBar(QWidget):
    """A slim gold-to-orange "power level" meter for indexing progress."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ratio = 0.0
        self.setFixedHeight(6)

    def set_ratio(self, ratio: float) -> None:
        self._ratio = max(0.0, min(1.0, ratio))
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 60))
        painter.drawRoundedRect(QRectF(self.rect()), 3, 3)
        filled = QRectF(0, 0, self.width() * self._ratio, self.height())
        gradient = QLinearGradient(filled.topLeft(), filled.topRight())
        gradient.setColorAt(0.0, QColor(CLOUD_GOLD))
        gradient.setColorAt(1.0, QColor(ENERGY_ORANGE))
        painter.setBrush(gradient)
        painter.drawRoundedRect(filled, 3, 3)


def _top_rounded_rect(rect: QRectF, radius: float) -> QPainterPath:
    """A rect with only its top corners rounded, to sit flush on the window's body."""
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    square_bottom = QPainterPath()
    square_bottom.addRect(QRectF(rect.x(), rect.center().y(), rect.width(), rect.height() / 2))
    return path.united(square_bottom)


def _with_alpha(hex_color: str, strength: float) -> QColor:
    color = QColor(hex_color)
    color.setAlphaF(0.35 + 0.65 * strength)
    return color
