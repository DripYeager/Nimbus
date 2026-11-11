from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtMultimedia import QAudioFormat

from ui.voice_recorder import (
    MAX_RECORDING_S,
    SPEECH_LEVEL,
    WAIT_FOR_SPEECH_S,
    SilenceWatcher,
    level,
    resample,
    to_mono_float,
)

LOUD, QUIET = SPEECH_LEVEL * 4, SPEECH_LEVEL / 4


def _format(kind: QAudioFormat.SampleFormat, channels: int, rate: int = 48_000) -> QAudioFormat:
    audio_format = QAudioFormat()
    audio_format.setSampleFormat(kind)
    audio_format.setChannelCount(channels)
    audio_format.setSampleRate(rate)
    return audio_format


def test_to_mono_float_averages_stereo_int16() -> None:
    raw = np.array([16384, 0, -16384, 0], dtype=np.int16).tobytes()

    samples = to_mono_float(raw, _format(QAudioFormat.SampleFormat.Int16, 2))

    assert samples.tolist() == pytest.approx([0.25, -0.25])


def test_to_mono_float_reads_float_samples() -> None:
    raw = np.array([0.5, -0.5], dtype=np.float32).tobytes()

    assert to_mono_float(raw, _format(QAudioFormat.SampleFormat.Float, 1)).tolist() == [0.5, -0.5]


def test_resample_brings_48k_down_to_16k() -> None:
    assert resample(np.zeros(48_000, dtype=np.float32), 48_000).size == 16_000


def test_level_of_silence_is_zero() -> None:
    assert level(np.zeros(100, dtype=np.float32)) == 0.0


def test_watcher_stops_after_a_pause_following_speech() -> None:
    watcher = SilenceWatcher()
    watcher.add(LOUD, 1.0)

    stops = [watcher.add(QUIET, 0.4) for _ in range(4)]

    # Stops once the quiet adds up to SILENCE_TO_STOP_S (1.2 s): on the third quiet chunk.
    assert stops == [False, False, True, True]


def test_watcher_keeps_going_while_the_speaker_talks() -> None:
    watcher = SilenceWatcher()

    assert not any(watcher.add(LOUD, 0.5) for _ in range(10))


def test_watcher_gives_up_when_nothing_is_said() -> None:
    watcher = SilenceWatcher()

    assert watcher.add(QUIET, WAIT_FOR_SPEECH_S) is True
    assert watcher.heard_speech is False


def test_watcher_stops_at_the_time_limit() -> None:
    watcher = SilenceWatcher()

    assert watcher.add(LOUD, MAX_RECORDING_S) is True
