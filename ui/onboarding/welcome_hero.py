"""
The welcome step's hero art: a rounded sky panel with speed lines streaking past a big golden
cloud, as if it just pulled up to collect you. Code-drawn and original; painting only.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPaintEvent, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from ui.theme.painting import paint_cloud
from ui.theme.tokens import CLOUD_GOLD, RADIUS_CARD, SKY_BOTTOM, SKY_TOP

HERO_HEIGHT = 210
CLOUD_WIDTH_RATIO = 0.42
CLOUD_ASPECT = 0.6
SUN_ALPHA = 90
# (x, y, length) as fractions of the panel, all streaking left of the cloud.
SPEED_LINES = (
    (0.06, 0.30, 0.22),
    (0.14, 0.46, 0.16),
    (0.03, 0.62, 0.20),
    (0.18, 0.74, 0.12),
    (0.70, 0.22, 0.18),
    (0.78, 0.80, 0.14),
)
LINE_ALPHA = 120
LINE_WIDTH = 3


class WelcomeHero(QWidget):
    """The sky panel; stretches horizontally and keeps a fixed height."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(HERO_HEIGHT)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        panel = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(panel, RADIUS_CARD, RADIUS_CARD)
        painter.setClipPath(clip)
        self._paint_sky(painter, panel)
        self._paint_speed_lines(painter, panel)
        paint_cloud(painter, self._cloud_rect(panel))

    def _cloud_rect(self, panel: QRectF) -> QRectF:
        width = panel.width() * CLOUD_WIDTH_RATIO
        height = min(width * CLOUD_ASPECT, panel.height() * 0.7)
        return QRectF(panel.center().x() - width / 2, panel.center().y() - height / 2, width, height)

    def _paint_sky(self, painter: QPainter, panel: QRectF) -> None:
        """A diagonal sky with a warm glow behind where the cloud sits."""
        sky = QLinearGradient(panel.topLeft(), panel.bottomRight())
        sky.setColorAt(0.0, QColor(SKY_TOP))
        sky.setColorAt(1.0, QColor(SKY_BOTTOM))
        painter.fillRect(panel, sky)
        sun = QColor(CLOUD_GOLD)
        sun.setAlpha(SUN_ALPHA)
        glow = QRadialGradient(panel.center(), panel.height() * 0.8)
        glow.setColorAt(0.0, sun)
        glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(panel, glow)

    def _paint_speed_lines(self, painter: QPainter, panel: QRectF) -> None:
        painter.setPen(QPen(QColor(255, 255, 255, LINE_ALPHA), LINE_WIDTH, cap=Qt.PenCapStyle.RoundCap))
        for x, y, length in SPEED_LINES:
            start = QPointF(panel.width() * x, panel.height() * y)
            painter.drawLine(start, QPointF(start.x() + panel.width() * length, start.y()))
