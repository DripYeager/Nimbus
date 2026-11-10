"""
The welcome screen of a new chat: the golden cloud cruising across a patch of sky with speed
lines trailing behind it, a comic-style "WHERE TO?" headline, and a grid of suggestion cards.
Display only — a clicked suggestion is reported through suggestion_clicked.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPaintEvent, QPen, QRadialGradient
from PyQt6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.theme.fonts import use_display_font
from ui.theme.glow_label import GlowLabel
from ui.theme.line_icons import line_icon
from ui.theme.painting import paint_cloud
from ui.theme.tokens import GI_ORANGE, SKY_BOTTOM

HERO_SIZE = QSize(260, 150)
HEADLINE_PX = 52
# Per halo copy; the copies stack into a soft orange glow.
HEADLINE_GLOW_ALPHA = 55
CRUISE_MS = 2600
SUGGESTION_ICON_SIZE = 18
# (icon, text) pairs; the text is what gets sent when a card is clicked.
SUGGESTIONS = [
    ("sparkles", "What did I download today?"),
    ("search", "Find my resume"),
    ("file-text", "Summarize the latest PDF in my Downloads"),
    ("app-window", "Open Notepad"),
    ("battery-medium", "How's my battery and disk space?"),
    ("notebook-pen", "Remember to renew my passport in May"),
]
# Speed lines as (vertical position, length) in hero-relative units.
SPEED_LINES = ((0.38, 0.30), (0.52, 0.42), (0.66, 0.24), (0.46, 0.18))


class CloudHero(QWidget):
    """The cloud bobbing on the spot as if flying, with streaks rushing past behind it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(HERO_SIZE)
        self._phase = 0.0
        self._cruise = QVariantAnimation(self)
        self._cruise.setStartValue(0.0)
        self._cruise.setEndValue(1.0)
        self._cruise.setDuration(CRUISE_MS)
        self._cruise.setLoopCount(-1)
        self._cruise.valueChanged.connect(self._advance)

    def showEvent(self, event: object) -> None:
        self._cruise.start()

    def hideEvent(self, event: object) -> None:
        self._cruise.stop()

    def _advance(self, value: float) -> None:
        self._phase = value
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        halo = QRadialGradient(QPointF(width / 2, height * 0.55), height * 0.6)
        sky = QColor(SKY_BOTTOM)
        sky.setAlphaF(0.20)
        halo.setColorAt(0.0, sky)
        halo.setColorAt(1.0, QColor(0, 0, 0, 0))
        # Filling the whole rect lets the gradient fade out on its own, with no visible edge.
        painter.fillRect(self.rect(), halo)
        self._paint_speed_lines(painter, width, height)
        bob = math.sin(self._phase * 2 * math.pi) * 4
        paint_cloud(painter, QRectF(width * 0.16, height * 0.22 + bob, width * 0.68, height * 0.5))

    def _paint_speed_lines(self, painter: QPainter, width: int, height: int) -> None:
        """Streaks that scroll right-to-left behind the cloud, fading at both ends."""
        for index, (y, length) in enumerate(SPEED_LINES):
            offset = (self._phase + index * 0.27) % 1.0
            x = width * (1.0 - offset) - width * 0.1
            alpha = int(150 * math.sin(offset * math.pi))
            painter.setPen(QPen(QColor(255, 255, 255, alpha), 2, cap=Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(x, height * y), QPointF(x + width * length, height * y))


class EmptyState(QWidget):
    """The welcome shown in a fresh chat."""

    suggestion_clicked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)
        layout.addWidget(CloudHero(self), alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(_headline(self), alignment=Qt.AlignmentFlag.AlignHCenter)
        subtitle = QLabel("Ask about your files, or tell me what to open.", self)
        subtitle.setObjectName("EmptySubtitle")
        layout.addWidget(subtitle, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(18)
        layout.addLayout(self._suggestion_grid())

    def _suggestion_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        for index, (icon, text) in enumerate(SUGGESTIONS):
            card = QPushButton(text, self)
            card.setObjectName("SuggestionCard")
            card.setIcon(line_icon(icon, GI_ORANGE, SUGGESTION_ICON_SIZE))
            card.setIconSize(QSize(SUGGESTION_ICON_SIZE, SUGGESTION_ICON_SIZE))
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.clicked.connect(lambda _=False, t=text: self.suggestion_clicked.emit(t))
            grid.addWidget(card, index // 2, index % 2)
        return grid


def _headline(parent: QWidget) -> QLabel:
    """WHERE TO? in the comic face, gold with an orange glow."""
    title = GlowLabel("WHERE TO?", QColor(255, 122, 26, HEADLINE_GLOW_ALPHA), parent)
    title.setObjectName("EmptyTitle")
    use_display_font(title, HEADLINE_PX)
    return title
