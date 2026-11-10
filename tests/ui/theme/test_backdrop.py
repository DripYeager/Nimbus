from __future__ import annotations

import pytest
from PyQt6.QtGui import QColor, QImage

from ui.theme.backdrop import STAR_COUNT, NightBackdrop
from ui.theme.tokens import NIGHT

SIZE = (240, 160)


@pytest.fixture
def backdrop() -> NightBackdrop:
    widget = NightBackdrop()
    widget.resize(*SIZE)
    return widget


def _render(backdrop: NightBackdrop) -> QImage:
    return backdrop.grab().toImage()


def test_night_backdrop_scatters_a_fixed_number_of_stars(backdrop: NightBackdrop) -> None:
    assert len(backdrop._stars) == STAR_COUNT


def test_night_backdrop_places_the_same_stars_every_time(backdrop: NightBackdrop) -> None:
    assert NightBackdrop()._stars == backdrop._stars


def test_night_backdrop_keeps_stars_in_the_upper_sky(backdrop: NightBackdrop) -> None:
    assert all(0.0 <= x <= 1.0 and 0.0 <= y <= 0.6 for x, y, _ in backdrop._stars)


def test_paint_event_fills_the_panel_with_the_night_colour(backdrop: NightBackdrop) -> None:
    centre = _render(backdrop).pixelColor(SIZE[0] // 2, SIZE[1] // 2)

    night = QColor(NIGHT)
    assert (
        abs(centre.red() - night.red()) + abs(centre.green() - night.green()) + abs(centre.blue() - night.blue()) < 60
    )


def test_paint_event_leaves_the_rounded_corners_unpainted(backdrop: NightBackdrop) -> None:
    assert _render(backdrop).pixelColor(0, 0) != _render(backdrop).pixelColor(SIZE[0] // 2, SIZE[1] // 2)
