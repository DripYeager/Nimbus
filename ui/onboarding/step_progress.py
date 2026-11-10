"""
The onboarding step tracker: numbered dots joined by a line, filled gi orange up to the current
step, each with a short caption. Painting only; which step is current is the wizard's call.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QWidget

from ui.theme.fonts import body_font
from ui.theme.tokens import BORDER_STRONG, GI_ORANGE, SURFACE, TEXT, TEXT_MUTED, TEXT_ON_ORANGE

DOT_SIZE = 24
HALO_SIZE = 34
HALO_ALPHA = 60
LINE_WIDTH = 2
CAPTION_GAP = 6
CAPTION_HEIGHT = 16
NUMBER_PX = 11
CAPTION_PX = 11
TRACKER_HEIGHT = HALO_SIZE + CAPTION_GAP + CAPTION_HEIGHT


class StepProgress(QWidget):
    """Shows len(captions) steps; set_step(index) moves the highlight."""

    def __init__(self, captions: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._captions = captions
        self._current = 0
        self.setFixedHeight(TRACKER_HEIGHT)

    def set_step(self, index: int) -> None:
        self._current = max(0, min(index, len(self._captions) - 1))
        self.update()

    def current_step(self) -> int:
        return self._current

    def _dot_center(self, index: int) -> QPointF:
        """Dots spread evenly, inset by half a caption so the outer captions aren't clipped."""
        inset = self.width() / (2 * len(self._captions))
        step = (self.width() - 2 * inset) / max(1, len(self._captions) - 1)
        return QPointF(inset + step * index, HALO_SIZE / 2)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_lines(painter)
        for index in range(len(self._captions)):
            self._paint_dot(painter, index)
            self._paint_caption(painter, index)

    def _paint_lines(self, painter: QPainter) -> None:
        """Orange between finished steps, a muted line ahead."""
        for index in range(len(self._captions) - 1):
            start, end = self._dot_center(index), self._dot_center(index + 1)
            color = GI_ORANGE if index < self._current else BORDER_STRONG
            painter.setPen(QPen(QColor(color), LINE_WIDTH))
            painter.drawLine(QPointF(start.x() + DOT_SIZE / 2, start.y()), QPointF(end.x() - DOT_SIZE / 2, end.y()))

    def _paint_dot(self, painter: QPainter, index: int) -> None:
        center = self._dot_center(index)
        is_reached = index <= self._current
        if index == self._current:
            halo = QColor(GI_ORANGE)
            halo.setAlpha(HALO_ALPHA)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(center, HALO_SIZE / 2, HALO_SIZE / 2)
        painter.setPen(Qt.PenStyle.NoPen if is_reached else QPen(QColor(BORDER_STRONG), LINE_WIDTH))
        painter.setBrush(QColor(GI_ORANGE if is_reached else SURFACE))
        painter.drawEllipse(center, DOT_SIZE / 2, DOT_SIZE / 2)
        painter.setPen(QColor(TEXT_ON_ORANGE if is_reached else TEXT_MUTED))
        number_font = body_font(NUMBER_PX)
        number_font.setBold(True)
        painter.setFont(number_font)
        dot_rect = QRectF(center.x() - DOT_SIZE / 2, center.y() - DOT_SIZE / 2, DOT_SIZE, DOT_SIZE)
        painter.drawText(dot_rect, Qt.AlignmentFlag.AlignCenter, str(index + 1))

    def _paint_caption(self, painter: QPainter, index: int) -> None:
        center = self._dot_center(index)
        width = self.width() / len(self._captions)
        rect = QRectF(center.x() - width / 2, HALO_SIZE + CAPTION_GAP, width, CAPTION_HEIGHT)
        painter.setPen(QColor(TEXT if index == self._current else TEXT_MUTED))
        painter.setFont(body_font(CAPTION_PX))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._captions[index])
