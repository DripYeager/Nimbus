from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QMouseEvent, QPixmap

from ui.screen_capture import KEEP_CAPTURES, RegionCapture, save_capture


def _mouse(kind: QMouseEvent.Type, point: QPoint, button: Qt.MouseButton = Qt.MouseButton.LeftButton) -> QMouseEvent:
    position = QPointF(point)
    return QMouseEvent(kind, position, position, button, button, Qt.KeyboardModifier.NoModifier)


def _drag(capture: RegionCapture, start: QPoint, end: QPoint) -> None:
    capture.mousePressEvent(_mouse(QMouseEvent.Type.MouseButtonPress, start))
    capture.mouseMoveEvent(_mouse(QMouseEvent.Type.MouseMove, end))
    capture.mouseReleaseEvent(_mouse(QMouseEvent.Type.MouseButtonRelease, end))


def test_save_capture_writes_a_png(tmp_path: Path, qapp: object) -> None:
    image = QPixmap(40, 20)
    image.fill(QColor("white"))

    path = save_capture(image, tmp_path)

    assert (path.suffix, path.exists()) == (".png", True)


def test_save_capture_keeps_only_the_latest_few(tmp_path: Path, qapp: object) -> None:
    for index in range(KEEP_CAPTURES + 3):
        (tmp_path / f"screenshot-2026{index:04d}.png").write_bytes(b"old")
    image = QPixmap(10, 10)
    image.fill(QColor("white"))

    save_capture(image, tmp_path)

    assert len(list(tmp_path.glob("screenshot-*.png"))) == KEEP_CAPTURES


def test_region_capture_emits_the_dragged_piece(qapp: object) -> None:
    capture = RegionCapture()
    pieces: list[QPixmap] = []
    capture.captured.connect(pieces.append)

    _drag(capture, QPoint(10, 10), QPoint(110, 60))

    ratio = capture._shot.devicePixelRatio()
    assert [(p.width(), p.height()) for p in pieces] == [(int(100 * ratio), int(50 * ratio))]


def test_region_capture_ignores_a_tiny_click(qapp: object) -> None:
    capture = RegionCapture()
    pieces: list[QPixmap] = []
    capture.captured.connect(pieces.append)

    _drag(capture, QPoint(10, 10), QPoint(12, 12))

    assert (pieces, capture.selection().isNull()) == ([], True)


def test_region_capture_right_click_cancels(qapp: object) -> None:
    capture = RegionCapture()
    cancelled: list[None] = []
    capture.cancelled.connect(lambda: cancelled.append(None))

    capture.mousePressEvent(_mouse(QMouseEvent.Type.MouseButtonPress, QPoint(5, 5), Qt.MouseButton.RightButton))

    assert cancelled == [None]
