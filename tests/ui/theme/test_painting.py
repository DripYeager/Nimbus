from __future__ import annotations

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from ui.theme.painting import AuraFrame, CloudGlyph, PowerBar, SkyHeader, _top_rounded_rect, cloud_path, paint_cloud


def _painted_pixels(pixmap: QPixmap) -> int:
    image = pixmap.toImage()
    return sum(1 for x in range(image.width()) for y in range(image.height()) if image.pixelColor(x, y).alpha() > 0)


@pytest.mark.parametrize("with_tail", [True, False])
def test_cloud_path_fills_most_of_the_rect(with_tail: bool) -> None:
    rect = QRectF(10, 10, 100, 60)

    bounds = cloud_path(rect, with_tail).boundingRect()

    assert not cloud_path(rect, with_tail).isEmpty()
    assert rect.adjusted(-1, -1, 1, 1).contains(bounds)
    assert bounds.width() > rect.width() * 0.75


def test_cloud_path_tail_reaches_the_right_edge() -> None:
    rect = QRectF(0, 0, 100, 60)

    with_tail = cloud_path(rect, with_tail=True).boundingRect()

    assert with_tail.right() == pytest.approx(rect.right(), abs=1)
    assert with_tail.right() > cloud_path(QRectF(0, 0, 78, 60), with_tail=False).boundingRect().right()


def test_paint_cloud_draws_inside_the_rect() -> None:
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)

    paint_cloud(painter, QRectF(4, 12, 56, 40))
    painter.end()

    assert _painted_pixels(pixmap) > 0


@pytest.mark.parametrize("phase", [0.0, 0.5])
def test_sky_header_paints_the_sky(phase: float) -> None:
    header = SkyHeader()
    header.resize(200, 64)
    header.streak_phase = phase

    image = header.grab().toImage()

    assert image.pixelColor(100, 40).blue() > image.pixelColor(100, 40).red()


def test_sky_header_streak_phase_round_trips() -> None:
    header = SkyHeader()

    header.streak_phase = 0.3

    assert header.streak_phase == pytest.approx(0.3)


def test_cloud_glyph_paints_with_an_offset() -> None:
    glyph = CloudGlyph(48)

    glyph.set_offset_y(3.0)

    assert _painted_pixels(glyph.grab()) > 0


@pytest.mark.parametrize("glow", [0.0, 0.6])
def test_aura_frame_paints_at_any_glow(glow: float) -> None:
    frame = AuraFrame()
    frame.resize(200, 50)
    frame.glow = glow

    assert not frame.grab().isNull()


def test_power_bar_clamps_the_ratio() -> None:
    bar = PowerBar()

    bar.set_ratio(1.7)

    assert bar._ratio == 1.0


def test_power_bar_clamps_negative_ratios() -> None:
    bar = PowerBar()

    bar.set_ratio(-0.5)

    assert bar._ratio == 0.0


def test_power_bar_paints() -> None:
    bar = PowerBar()
    bar.resize(140, 6)
    bar.set_ratio(0.5)

    assert not bar.grab().isNull()


def test_top_rounded_rect_keeps_bottom_corners_square() -> None:
    path = _top_rounded_rect(QRectF(0, 0, 100, 40), 18)

    assert path.contains(QRectF(0, 39, 1, 1).center())
    assert not path.contains(QRectF(0, 0, 1, 1).center())


def test_widgets_paint_inside_a_parent_without_errors() -> None:
    parent = QWidget()
    parent.resize(300, 120)
    SkyHeader(parent).resize(300, 64)
    CloudGlyph(40, parent)

    image = parent.grab().toImage()

    assert image.pixelColor(150, 30).blue() > image.pixelColor(150, 30).red()
