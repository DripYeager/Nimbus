from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QImage
from pytest_mock import MockerFixture

from ui.theme.line_icons import SUPERSAMPLE, _tinted_svg, line_icon, line_pixmap

RED = "#FF0000"
BLUE = "#0000FF"


@pytest.fixture(autouse=True)
def fresh_cache() -> Iterator[None]:
    """Each test sees icons loaded from disk, not ones an earlier test cached."""
    line_pixmap.cache_clear()
    _tinted_svg.cache_clear()
    yield
    line_pixmap.cache_clear()
    _tinted_svg.cache_clear()


@pytest.fixture
def logger(mocker: MockerFixture) -> Mock:
    return mocker.patch("ui.theme.line_icons.logger")


def _opaque_colours(image: QImage) -> set[str]:
    return {
        image.pixelColor(x, y).name()
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() == 255
    }


def test_tinted_svg_replaces_current_color() -> None:
    svg = _tinted_svg("check", RED, "2").decode("utf-8")

    assert (RED in svg, "currentColor" in svg) == (True, False)


def test_tinted_svg_sets_the_stroke_width() -> None:
    assert b'stroke-width="1.5"' in _tinted_svg("check", RED, "1.5")


def test_tinted_svg_returns_none_for_a_missing_icon(logger: Mock) -> None:
    assert _tinted_svg("no-such-icon", RED, "2") is None


def test_tinted_svg_logs_a_missing_icon(logger: Mock) -> None:
    _tinted_svg("no-such-icon", RED, "2")

    logger.warning.assert_called_once_with("Missing icon", extra={"icon": "no-such-icon"})


def test_line_pixmap_renders_at_twice_the_size_for_high_dpi() -> None:
    pixmap = line_pixmap("check", RED, 16)

    assert (pixmap.width(), pixmap.devicePixelRatio()) == (16 * SUPERSAMPLE, SUPERSAMPLE)


def test_line_pixmap_draws_in_the_requested_colour() -> None:
    assert _opaque_colours(line_pixmap("check", RED, 16).toImage()) == {QColor(RED).name()}


def test_line_pixmap_returns_a_transparent_pixmap_for_a_missing_icon(logger: Mock) -> None:
    image = line_pixmap("no-such-icon", RED, 16).toImage()

    assert {image.pixelColor(x, y).alpha() for x in range(image.width()) for y in range(image.height())} == {0}


def test_line_pixmap_returns_the_cached_pixmap_for_the_same_request() -> None:
    assert line_pixmap("check", RED, 16) is line_pixmap("check", RED, 16)


def test_line_pixmap_draws_a_new_pixmap_for_another_colour() -> None:
    assert line_pixmap("check", RED, 16) is not line_pixmap("check", BLUE, 16)


def test_line_icon_uses_the_colour_normally() -> None:
    image = line_icon("check", RED, 16, hover_color=BLUE).pixmap(32, 32, QIcon.Mode.Normal).toImage()

    assert QColor(RED).name() in _opaque_colours(image)


def test_line_icon_uses_the_hover_colour_when_active() -> None:
    image = line_icon("check", RED, 16, hover_color=BLUE).pixmap(32, 32, QIcon.Mode.Active).toImage()

    assert QColor(BLUE).name() in _opaque_colours(image)


def test_line_pixmap_starts_from_a_transparent_background() -> None:
    assert line_pixmap("check", RED, 16).toImage().pixelColor(0, 0) == QColor(Qt.GlobalColor.transparent)
