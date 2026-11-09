from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from PyQt6.QtCore import QSize

from ui.theme.icons import ICON_SIZES, app_icon, export_icon_files, render_icon


@pytest.mark.parametrize("size", [16, 32, 256])
def test_render_icon_returns_a_square_of_the_requested_size(size: int) -> None:
    pixmap = render_icon(size)

    assert (pixmap.width(), pixmap.height()) == (size, size)


def test_render_icon_keeps_the_corners_transparent() -> None:
    image = render_icon(64).toImage()

    assert image.pixelColor(0, 0).alpha() == 0


def test_render_icon_draws_the_cloud_in_the_middle() -> None:
    image = render_icon(64, with_tail=False).toImage()

    assert image.pixelColor(32, 32).alpha() == 255


def test_app_icon_offers_every_size() -> None:
    sizes = app_icon().availableSizes()

    assert sizes == [QSize(s, s) for s in ICON_SIZES]


def test_export_icon_files_writes_png_and_ico(tmp_path: Path) -> None:
    png_path, ico_path = export_icon_files(tmp_path / "assets")

    with Image.open(png_path) as png:
        assert png.size == (256, 256)
    with Image.open(ico_path) as ico:
        assert ico.format == "ICO"


def test_export_icon_files_creates_missing_directories(tmp_path: Path) -> None:
    target = tmp_path / "build" / "icons"

    export_icon_files(target)

    assert sorted(p.name for p in target.iterdir()) == ["nimbus.ico", "nimbus.png"]
