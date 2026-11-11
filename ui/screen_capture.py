"""
Lets the user drag a box over part of the screen and hands back that piece as an image, for
"ask about something on screen". A frozen, dimmed copy of the screen under the mouse fills a
frameless overlay; the box shows the real pixels. Esc or a right click cancels. Also saves
captures where the engine can read them. Owns capture only; reading the text is the engine's job.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

from config.settings import get_settings
from ui.theme.tokens import GI_ORANGE

DIM_ALPHA = 120
MIN_SELECTION_PX = 8
KEEP_CAPTURES = 20
CAPTURE_FOLDER = "screenshots"
HINT_TEXT = "Drag over what you want to ask about  ·  Esc to cancel"
HINT_MARGIN_PX = 24


class RegionCapture(QWidget):
    """A one-shot overlay: emits captured(QPixmap) or cancelled, then closes itself."""

    captured = pyqtSignal(QPixmap)
    cancelled = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self._shot = screen.grabWindow(0)
        self._origin: QPoint | None = None
        self._selection = QRect()
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(screen.geometry())

    def start(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def selection(self) -> QRect:
        return QRect(self._selection)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._shot)
        painter.fillRect(self.rect(), QColor(0, 0, 0, DIM_ALPHA))
        if not self._selection.isNull():
            painter.drawPixmap(self._selection, self._shot, self._source_rect(self._selection))
            painter.setPen(QPen(QColor(GI_ORANGE), 2))
            painter.drawRect(self._selection)
        else:
            painter.setPen(QColor("white"))
            painter.drawText(self.rect().adjusted(0, HINT_MARGIN_PX, 0, 0), Qt.AlignmentFlag.AlignHCenter, HINT_TEXT)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._cancel()
            return
        self._origin = event.position().toPoint()
        self._selection = QRect(self._origin, self._origin)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._origin is not None:
            self._selection = _box(self._origin, event.position().toPoint())
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._origin is None:
            return
        self._origin = None
        if self._selection.width() < MIN_SELECTION_PX or self._selection.height() < MIN_SELECTION_PX:
            self._selection = QRect()
            self.update()
            return
        piece = self._shot.copy(self._source_rect(self._selection))
        self.close()
        self.captured.emit(piece)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()

    def _cancel(self) -> None:
        self.close()
        self.cancelled.emit()

    def _source_rect(self, rect: QRect) -> QRect:
        """rect in the screenshot's own pixels, which are denser on a scaled display."""
        ratio = self._shot.devicePixelRatio()
        x, y, width, height = (int(value * ratio) for value in (rect.x(), rect.y(), rect.width(), rect.height()))
        return QRect(x, y, width, height)


def _box(corner: QPoint, opposite: QPoint) -> QRect:
    """The rectangle between two corners, exactly as wide as the drag (QRect's two-point form
    counts both edge pixels)."""
    left, top = min(corner.x(), opposite.x()), min(corner.y(), opposite.y())
    return QRect(left, top, abs(opposite.x() - corner.x()), abs(opposite.y() - corner.y()))


def save_capture(image: QPixmap, folder: Path | None = None) -> Path:
    """Saves a capture as PNG in Nimbus's data folder, keeping only the most recent few."""
    target = folder or get_settings().data_dir / CAPTURE_FOLDER
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"screenshot-{datetime.now():%Y%m%d-%H%M%S-%f}.png"
    image.save(str(path), "PNG")
    for old in sorted(target.glob("screenshot-*.png"))[:-KEEP_CAPTURES]:
        old.unlink(missing_ok=True)
    return path
