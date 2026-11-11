from __future__ import annotations

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QImage, QPainter

from ui.theme.soft_shadow import SHADOW_DROP_PX, SoftShadow, _shadow_image

CANVAS = QSize(200, 200)
PANEL = QRect(30, 30, 140, 140)


def test_shadow_image_is_darkest_next_to_the_panel(qapp: object) -> None:
    image = _shadow_image(CANVAS, PANEL, 10)

    near = image.pixelColor(100, PANEL.bottom() + SHADOW_DROP_PX + 1).alpha()
    far = image.pixelColor(100, PANEL.bottom() + SHADOW_DROP_PX + 18).alpha()

    assert near > far > 0


def test_shadow_image_leaves_the_far_corner_clear(qapp: object) -> None:
    assert _shadow_image(CANVAS, PANEL, 10).pixelColor(0, 0).alpha() == 0


def test_paint_reuses_the_cached_image_for_the_same_sizes(qapp: object, mocker: object) -> None:
    build = mocker.patch("ui.theme.soft_shadow._shadow_image", wraps=_shadow_image)
    shadow = SoftShadow(10)
    target = QImage(CANVAS, QImage.Format.Format_ARGB32_Premultiplied)
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)

    shadow.paint(painter, CANVAS, PANEL)
    shadow.paint(painter, CANVAS, PANEL)
    painter.end()

    assert build.call_count == 1
