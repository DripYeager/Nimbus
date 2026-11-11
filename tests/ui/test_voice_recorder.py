from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtMultimedia import QAudioFormat
from pytest_mock import MockerFixture

from ui.voice_recorder import (
    MAX_RECORDING_S,
    MIC_STOPPED_MESSAGE,
    NO_AUDIO_TIMEOUT_S,
    SPEECH_LEVEL,
    WAIT_FOR_SPEECH_S,
    SilenceWatcher,
    VoiceRecorder,
    level,
    resample,
    split_frames,
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


def test_to_mono_float_drops_a_trailing_partial_frame() -> None:
    raw = np.array([16384], dtype=np.int16).tobytes() + b"\x00"

    samples = to_mono_float(raw, _format(QAudioFormat.SampleFormat.Int16, 1))

    assert samples.tolist() == pytest.approx([0.5])


def test_to_mono_float_of_only_a_partial_frame_is_empty() -> None:
    assert to_mono_float(b"\x00", _format(QAudioFormat.SampleFormat.Int16, 1)).size == 0


def test_stop_finishes_once_when_the_device_stops_reentrantly(qapp: object) -> None:
    from unittest.mock import Mock

    from ui.voice_recorder import VoiceRecorder

    recorder = VoiceRecorder()
    recorder._format = _format(QAudioFormat.SampleFormat.Int16, 1, 16_000)
    recorder._chunks = [np.ones(160, dtype=np.float32)]
    source = Mock()

    def stop_again() -> None:
        recorder.stop()

    source.stop.side_effect = stop_again
    recorder._source = source
    recorder._stream = Mock()
    recorder._stream.readAll.return_value = b""
    finished: list[np.ndarray] = []
    recorder.finished.connect(finished.append)

    recorder.stop()

    assert (len(finished), finished[0].size) == (1, 160)


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


def test_split_frames_keeps_a_partial_frame_for_later() -> None:
    audio_format = _format(QAudioFormat.SampleFormat.Int16, 1)

    assert split_frames(b"\x01\x02\x03", audio_format) == (b"\x01\x02", b"\x03")


def test_a_sample_split_across_two_reads_is_put_back_together(qapp: object) -> None:
    recorder = VoiceRecorder()
    recorder._format = _format(QAudioFormat.SampleFormat.Int16, 1, 16_000)
    raw = np.array([1000, -2000, 3000], dtype=np.int16).tobytes()

    recorder._keep(raw[:3])
    recorder._keep(raw[3:])

    samples = np.concatenate(recorder._chunks)
    assert (samples * 2**15).round().tolist() == [1000, -2000, 3000]


def _recording(recorder: VoiceRecorder, mocker: MockerFixture, started: float) -> None:
    """Puts the recorder in its recording state with a stand-in device."""
    recorder._source = mocker.Mock()
    recorder._stream = mocker.Mock(readAll=mocker.Mock(return_value=b""))
    recorder._format = _format(QAudioFormat.SampleFormat.Int16, 1, 16_000)
    recorder._started_at = recorder._last_audio_at = started


def test_watchdog_fails_a_recording_whose_device_went_quiet(qapp: object, mocker: MockerFixture) -> None:
    recorder = VoiceRecorder()
    _recording(recorder, mocker, started=100.0)
    failures: list[str] = []
    recorder.failed.connect(failures.append)
    mocker.patch("ui.voice_recorder.time.monotonic", return_value=100.0 + NO_AUDIO_TIMEOUT_S)

    recorder._check_alive()

    assert (failures, recorder.is_recording()) == ([MIC_STOPPED_MESSAGE], False)


def test_watchdog_ends_a_recording_at_the_time_limit(qapp: object, mocker: MockerFixture) -> None:
    recorder = VoiceRecorder()
    _recording(recorder, mocker, started=100.0)
    recorder._last_audio_at = 100.0 + MAX_RECORDING_S
    finished: list[object] = []
    recorder.finished.connect(finished.append)
    mocker.patch("ui.voice_recorder.time.monotonic", return_value=100.0 + MAX_RECORDING_S)

    recorder._check_alive()

    assert (len(finished), recorder.is_recording()) == (1, False)


def test_watchdog_leaves_a_healthy_recording_alone(qapp: object, mocker: MockerFixture) -> None:
    recorder = VoiceRecorder()
    _recording(recorder, mocker, started=100.0)
    mocker.patch("ui.voice_recorder.time.monotonic", return_value=101.0)

    recorder._check_alive()

    assert recorder.is_recording()
