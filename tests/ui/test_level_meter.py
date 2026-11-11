from __future__ import annotations

import pytest

from ui.widgets.level_meter import FULL_SCALE, LevelMeter


@pytest.fixture
def meter(qapp: object) -> LevelMeter:
    return LevelMeter()


def test_set_level_fills_the_meter_at_full_scale(meter: LevelMeter) -> None:
    meter.set_level(FULL_SCALE * 2)

    assert meter.level() == 1.0


def test_set_level_boosts_quiet_speech(meter: LevelMeter) -> None:
    meter.set_level(FULL_SCALE / 4)

    assert meter.level() == pytest.approx(0.5)


def test_set_level_falls_gradually(meter: LevelMeter) -> None:
    meter.set_level(FULL_SCALE)

    meter.set_level(0.0)

    assert 0.0 < meter.level() < 1.0


def test_reset_empties_the_meter(meter: LevelMeter) -> None:
    meter.set_level(FULL_SCALE)

    meter.reset()

    assert meter.level() == 0.0


def test_paint_draws_at_any_level(meter: LevelMeter) -> None:
    meter.resize(meter.sizeHint())
    for loudness in (0.0, FULL_SCALE / 3, FULL_SCALE):
        meter.set_level(loudness)
        assert not meter.grab().isNull()
