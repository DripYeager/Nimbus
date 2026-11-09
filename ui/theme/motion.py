"""
Builds the UI's animations: the window gliding in on summon and away on dismiss, the header's
speed-line sweep, the thinking glyph's bob, and the input aura's pulse. Construction only —
callers start them and must keep a reference, since an unreferenced animation is garbage-
collected mid-run.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QVariantAnimation,
)

from ui.theme.painting import AuraFrame, CloudGlyph, SkyHeader
from ui.theme.tokens import (
    AURA_PERIOD_MS,
    BOB_AMPLITUDE_PX,
    BOB_PERIOD_MS,
    DISMISS_MS,
    SUMMON_MS,
    SUMMON_RISE_PX,
)

BOB_SAMPLES = 16


def build_summon_animation(window: QObject, final_pos: QPoint, header: SkyHeader) -> QParallelAnimationGroup:
    """Glides up into final_pos while fading in, with the header's streaks sweeping past —
    a quick arrival that settles without overshoot."""
    start_pos = QPoint(final_pos.x(), final_pos.y() + SUMMON_RISE_PX)
    group = QParallelAnimationGroup(window)
    group.addAnimation(_animate(window, b"pos", (start_pos, final_pos), SUMMON_MS))
    group.addAnimation(_animate(window, b"windowOpacity", (0.0, 1.0), SUMMON_MS))
    group.addAnimation(_animate(header, b"streak_phase", (0.0, 1.0), SUMMON_MS * 3))
    return group


def build_dismiss_animation(window: QObject, start_pos: QPoint) -> QParallelAnimationGroup:
    """The mirror of summon, slightly faster — leaving should feel immediate."""
    end_pos = QPoint(start_pos.x(), start_pos.y() + SUMMON_RISE_PX)
    group = QParallelAnimationGroup(window)
    group.addAnimation(_animate(window, b"pos", (start_pos, end_pos), DISMISS_MS))
    group.addAnimation(_animate(window, b"windowOpacity", (1.0, 0.0), DISMISS_MS))
    return group


def build_bob_animation(glyph: CloudGlyph) -> QVariantAnimation:
    """Loops the glyph ±3px on a sine-like curve until stopped."""
    animation = QVariantAnimation(glyph)
    animation.setDuration(BOB_PERIOD_MS)
    animation.setLoopCount(-1)
    # Sampling the sine directly gives an even bob; an easing curve would apply across the whole
    # loop rather than per segment and make it linger at rest.
    for index in range(BOB_SAMPLES + 1):
        step = index / BOB_SAMPLES
        animation.setKeyValueAt(step, -BOB_AMPLITUDE_PX * math.sin(2 * math.pi * step))
    animation.valueChanged.connect(glyph.set_offset_y)
    return animation


def build_aura_animation(frame: AuraFrame) -> QPropertyAnimation:
    """Pulses the input's glow between soft and bright until stopped."""
    animation = QPropertyAnimation(frame, b"glow", frame)
    animation.setDuration(AURA_PERIOD_MS)
    animation.setLoopCount(-1)
    animation.setKeyValueAt(0.0, 0.25)
    animation.setKeyValueAt(0.5, 1.0)
    animation.setKeyValueAt(1.0, 0.25)
    animation.setEasingCurve(QEasingCurve.Type.InOutSine)
    return animation


def stop_animation(animation: QAbstractAnimation | None) -> None:
    """Stops an animation that may or may not exist or be running."""
    if animation is not None and animation.state() != QAbstractAnimation.State.Stopped:
        animation.stop()


def _animate(target: QObject, prop: bytes, values: tuple[object, object], duration_ms: int) -> QPropertyAnimation:
    """One OutCubic property animation from values[0] to values[1]."""
    animation = QPropertyAnimation(target, prop)
    animation.setDuration(duration_ms)
    animation.setStartValue(values[0])
    animation.setEndValue(values[1])
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    return animation
