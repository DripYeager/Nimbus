from __future__ import annotations

import pytest
from PyQt6.QtCore import QAbstractAnimation, QPoint, QPropertyAnimation, QVariantAnimation
from PyQt6.QtWidgets import QWidget

from ui.theme.motion import (
    build_aura_animation,
    build_bob_animation,
    build_dismiss_animation,
    build_summon_animation,
    stop_animation,
)
from ui.theme.painting import AuraFrame, CloudGlyph, SkyHeader
from ui.theme.tokens import BOB_AMPLITUDE_PX, DISMISS_MS, SUMMON_MS, SUMMON_RISE_PX


@pytest.fixture
def window() -> QWidget:
    return QWidget()


def _animations(group: QAbstractAnimation) -> list[QPropertyAnimation]:
    return [group.animationAt(i) for i in range(group.animationCount())]


def test_build_summon_animation_rises_into_place(window: QWidget) -> None:
    group = build_summon_animation(window, QPoint(100, 200), SkyHeader())

    position = _animations(group)[0]
    assert (position.startValue(), position.endValue()) == (QPoint(100, 200 + SUMMON_RISE_PX), QPoint(100, 200))
    assert position.duration() == SUMMON_MS


def test_build_summon_animation_fades_in_and_sweeps_the_header(window: QWidget) -> None:
    header = SkyHeader()

    group = build_summon_animation(window, QPoint(0, 0), header)

    names = [(bytes(a.propertyName()), a.targetObject()) for a in _animations(group)]
    assert names == [(b"pos", window), (b"windowOpacity", window), (b"streak_phase", header)]


def test_build_summon_animation_moves_the_window_when_run(window: QWidget) -> None:
    group = build_summon_animation(window, QPoint(40, 50), SkyHeader())

    group.start()
    group.setCurrentTime(group.totalDuration())

    assert window.pos() == QPoint(40, 50)


def test_build_dismiss_animation_sinks_and_fades(window: QWidget) -> None:
    group = build_dismiss_animation(window, QPoint(10, 20))

    position, opacity = _animations(group)
    assert position.endValue() == QPoint(10, 20 + SUMMON_RISE_PX)
    assert (opacity.startValue(), opacity.endValue(), opacity.duration()) == (1.0, 0.0, DISMISS_MS)


def test_build_bob_animation_loops_and_moves_the_glyph() -> None:
    glyph = CloudGlyph(30)
    animation = build_bob_animation(glyph)

    animation.start()
    animation.setCurrentTime(animation.duration() // 4)

    assert animation.loopCount() == -1
    assert -BOB_AMPLITUDE_PX <= glyph._offset_y < 0
    animation.stop()


def test_build_aura_animation_pulses_the_glow() -> None:
    frame = AuraFrame()
    animation = build_aura_animation(frame)

    animation.start()
    animation.setCurrentTime(animation.duration() // 2)

    assert frame.glow == pytest.approx(1.0, abs=0.01)
    animation.stop()


def test_stop_animation_stops_a_running_animation() -> None:
    animation = QVariantAnimation()
    animation.setDuration(1000)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.start()

    stop_animation(animation)

    assert animation.state() == QAbstractAnimation.State.Stopped


def test_stop_animation_accepts_none() -> None:
    stop_animation(None)


def test_stop_animation_leaves_a_stopped_animation_alone() -> None:
    animation = QVariantAnimation()

    stop_animation(animation)

    assert animation.state() == QAbstractAnimation.State.Stopped
