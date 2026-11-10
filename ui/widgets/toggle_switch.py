"""
A modern on/off switch: a pill track that fills with gi orange and a knob that slides across.
A drop-in replacement for a checkbox (it is a checkable button, so toggled/isChecked work the
same). Drawing and the slide animation only.
"""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, pyqtProperty
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import QAbstractButton, QWidget

from ui.theme.tokens import BORDER_STRONG, GI_ORANGE, SURFACE_HOVER, TEXT

TRACK_WIDTH, TRACK_HEIGHT = 40, 22
KNOB_MARGIN = 3
SLIDE_MS = 140


class ToggleSwitch(QAbstractButton):
    """Checkable switch; emits toggled(bool) like any QAbstractButton."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._position = 0.0
        self._slide = QPropertyAnimation(self, b"knob_position", self)
        self._slide.setDuration(SLIDE_MS)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate_to)

    def _get_position(self) -> float:
        return self._position

    def _set_position(self, value: float) -> None:
        self._position = value
        self.update()

    knob_position = pyqtProperty(float, fget=_get_position, fset=_set_position)

    def sizeHint(self) -> QSize:
        return QSize(TRACK_WIDTH, TRACK_HEIGHT)

    def setChecked(self, checked: bool) -> None:
        """Programmatic changes jump straight to the end position, no animation on load."""
        super().setChecked(checked)
        self._slide.stop()
        self._position = 1.0 if checked else 0.0
        self.update()

    def _animate_to(self, checked: bool) -> None:
        self._slide.stop()
        self._slide.setStartValue(self._position)
        self._slide.setEndValue(1.0 if checked else 0.0)
        self._slide.start()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        if not self.isEnabled():
            painter.setOpacity(0.45)
        track = QRectF(0, (self.height() - TRACK_HEIGHT) / 2, TRACK_WIDTH, TRACK_HEIGHT)
        off, on = QColor(SURFACE_HOVER), QColor(GI_ORANGE)
        blend = QColor.fromRgbF(
            off.redF() + (on.redF() - off.redF()) * self._position,
            off.greenF() + (on.greenF() - off.greenF()) * self._position,
            off.blueF() + (on.blueF() - off.blueF()) * self._position,
        )
        painter.setBrush(blend)
        if self._position < 1.0:
            painter.setPen(QColor(BORDER_STRONG))
        painter.drawRoundedRect(track, TRACK_HEIGHT / 2, TRACK_HEIGHT / 2)
        knob = TRACK_HEIGHT - 2 * KNOB_MARGIN
        x = track.x() + KNOB_MARGIN + (TRACK_WIDTH - knob - 2 * KNOB_MARGIN) * self._position
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(TEXT))
        painter.drawEllipse(QRectF(x, track.y() + KNOB_MARGIN, knob, knob))
