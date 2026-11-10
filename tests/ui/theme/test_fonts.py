from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication, QLabel
from pytest_mock import MockerFixture

from ui.theme.fonts import body_font, display_font, load_bundled_fonts, mono_font, use_display_font
from ui.theme.stylesheet import build_stylesheet
from ui.theme.tokens import DISPLAY_FONT_FAMILY, FONT_FALLBACK, FONT_FAMILY, MONO_FONT_FAMILY


@pytest.fixture
def app_stylesheet(qapp: QApplication) -> Iterator[None]:
    """The real app stylesheet, put back to whatever it was afterwards."""
    load_bundled_fonts()
    previous = qapp.styleSheet()
    qapp.setStyleSheet(build_stylesheet())
    yield
    qapp.setStyleSheet(previous)


@pytest.fixture
def logger(mocker: MockerFixture) -> Mock:
    return mocker.patch("ui.theme.fonts.logger")


def test_load_bundled_fonts_registers_the_display_face() -> None:
    load_bundled_fonts()

    assert DISPLAY_FONT_FAMILY in QFontDatabase.families()


def test_load_bundled_fonts_does_not_warn_when_the_fonts_load(logger: Mock) -> None:
    load_bundled_fonts()

    logger.warning.assert_not_called()


def test_load_bundled_fonts_warns_when_a_font_is_missing(mocker: MockerFixture, logger: Mock, tmp_path: Path) -> None:
    mocker.patch("ui.theme.fonts.asset_path", return_value=tmp_path / "missing.ttf")

    load_bundled_fonts()

    logger.warning.assert_called_once()


def test_display_font_prefers_the_comic_face_with_a_heavy_fallback() -> None:
    assert display_font(30).families() == [DISPLAY_FONT_FAMILY, "Segoe UI Black"]


def test_display_font_uses_the_pixel_size() -> None:
    assert display_font(30).pixelSize() == 30


def test_body_font_uses_the_reading_face_and_weight() -> None:
    font = body_font(14, QFont.Weight.Bold)

    assert (font.families(), font.pixelSize(), font.weight()) == (
        [FONT_FAMILY, FONT_FALLBACK],
        14,
        QFont.Weight.Bold,
    )


def test_body_font_defaults_to_normal_weight() -> None:
    assert body_font(14).weight() == QFont.Weight.Normal


def test_mono_font_uses_the_readout_face() -> None:
    font = mono_font(12)

    assert (font.families(), font.pixelSize()) == ([MONO_FONT_FAMILY, "Consolas"], 12)


def test_use_display_font_opts_the_widget_into_the_display_rule() -> None:
    label = QLabel("NIMBUS")

    use_display_font(label, 30)

    assert label.property("display") == "true"


def test_use_display_font_survives_the_app_stylesheet(app_stylesheet: None) -> None:
    label = QLabel("NIMBUS")
    use_display_font(label, 30)

    label.ensurePolished()

    assert label.font().family() == DISPLAY_FONT_FAMILY


def test_use_display_font_keeps_its_size_under_the_app_stylesheet(app_stylesheet: None) -> None:
    label = QLabel("NIMBUS")
    use_display_font(label, 30)

    label.ensurePolished()

    assert label.font().pixelSize() == 30


def test_plain_widgets_get_the_body_face_from_the_app_stylesheet(app_stylesheet: None) -> None:
    label = QLabel("text")

    label.ensurePolished()

    assert label.font().family() == FONT_FAMILY
