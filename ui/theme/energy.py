"""
The "ki" pieces of the theme, all code-drawn and original: a glowing energy orb that pulses
while Nimbus is working, and a scouter-style power-level readout for indexing progress.
Painting and their own idle animation only — callers decide when they show.
"""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, pyqtProperty
from PyQt6.QtGui import QColor, QPainter, QPaintEvent, QRadialGradient
from PyQt6.QtWidgets import QWidget

from ui.theme.fonts import mono_font
from ui.theme.tokens import CLOUD_GOLD, GI_ORANGE, GI_ORANGE_DEEP, ORB_PULSE_MS, SCOUTER_GREEN

ORB_REST_GLOW = 0.35


class EnergyOrb(QWidget):
    """A glowing orange orb; start() makes it pulse like it's charging, stop() lets it rest."""

    def __init__(self, size: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._glow = ORB_REST_GLOW
        self._pulse = QPropertyAnimation(self, b"glow", self)
        self._pulse.setDuration(ORB_PULSE_MS)
        self._pulse.setLoopCount(-1)
        self._pulse.setKeyValueAt(0.0, ORB_REST_GLOW)
        self._pulse.setKeyValueAt(0.5, 1.0)
        self._pulse.setKeyValueAt(1.0, ORB_REST_GLOW)
        self._pulse.setEasingCurve(QEasingCurve.Type.InOutSine)

    def _get_glow(self) -> float:
        return self._glow

    def _set_glow(self, value: float) -> None:
        self._glow = value
        self.update()

    glow = pyqtProperty(float, fget=_get_glow, fset=_set_glow)

    def start(self) -> None:
        self._pulse.start()

    def stop(self) -> None:
        self._pulse.stop()
        self.glow = ORB_REST_GLOW

    def paintEvent(self, event: QPaintEvent) -> None:
        """An outer halo that swells with glow, a hot core, and a small highlight."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        center = QPointF(self.width() / 2, self.height() / 2)
        radius = min(self.width(), self.height()) / 2
        painter.setBrush(_radial(center, radius, [(0.0, GI_ORANGE, 0.55 * self._glow), (1.0, GI_ORANGE, 0.0)]))
        painter.drawEllipse(center, radius, radius)
        core = radius * 0.55
        painter.setBrush(
            _radial(center, core, [(0.0, "#FFF4C2", 1.0), (0.45, CLOUD_GOLD, 1.0), (1.0, GI_ORANGE_DEEP, 1.0)])
        )
        painter.drawEllipse(center, core, core)
        painter.setBrush(QColor(255, 255, 255, 170))
        painter.drawEllipse(QPointF(center.x() - core * 0.35, center.y() - core * 0.4), core * 0.22, core * 0.16)


class PowerLevelReadout(QWidget):
    """A scouter-style HUD line: a green monospace "POWER LEVEL 1,240" with a thin scan bar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = 0
        self._ratio = 0.0
        self.setFixedHeight(28)
        self.setMinimumWidth(170)

    def set_progress(self, value: int, ratio: float) -> None:
        self._value = value
        self._ratio = max(0.0, min(1.0, ratio))
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        green = QColor(SCOUTER_GREEN)
        painter.setFont(mono_font(12))
        painter.setPen(green)
        painter.drawText(QRectF(0, 0, self.width(), 16), Qt.AlignmentFlag.AlignLeft, f"POWER LEVEL {self._value:,}")
        track = QRectF(0, 20, self.width(), 4)
        faint = QColor(green)
        faint.setAlphaF(0.18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(faint)
        painter.drawRoundedRect(track, 2, 2)
        painter.setBrush(green)
        painter.drawRoundedRect(QRectF(track.x(), track.y(), track.width() * self._ratio, track.height()), 2, 2)


def _radial(center: QPointF, radius: float, stops: list[tuple[float, str, float]]) -> QRadialGradient:
    """A radial gradient from (position, colour, alpha) stops."""
    gradient = QRadialGradient(center, radius)
    for position, hex_color, alpha in stops:
        color = QColor(hex_color)
        color.setAlphaF(alpha)
        gradient.setColorAt(position, color)
    return gradient
