"""
Records one utterance from the default microphone through Qt Multimedia: starts on start(),
stops on its own a moment after the speaker goes quiet (or after a time limit, or when nothing
is said at all), or early on stop(). Hands back 16 kHz mono samples, converting from whatever
format the device actually records in. Owns capture only; transcription is core/transcriber.py's.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QIODevice, QObject, pyqtSignal
from PyQt6.QtMultimedia import QAudioDevice, QAudioFormat, QAudioSource, QMediaDevices

TARGET_RATE = 16_000
# Loudness (RMS of samples in [-1, 1]) that counts as speech rather than room noise.
SPEECH_LEVEL = 0.015
SILENCE_TO_STOP_S = 1.2
WAIT_FOR_SPEECH_S = 6.0
MAX_RECORDING_S = 30.0
NO_MICROPHONE_MESSAGE = "No microphone was found. Plug one in, or check Settings > Privacy & security > Microphone."


def to_mono_float(raw: bytes, audio_format: QAudioFormat) -> np.ndarray:
    """Raw device bytes as mono float samples in [-1, 1], at the device's own rate."""
    kind = audio_format.sampleFormat()
    if kind == QAudioFormat.SampleFormat.Float:
        samples = np.frombuffer(raw, dtype=np.float32)
    elif kind == QAudioFormat.SampleFormat.Int32:
        samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2**31
    elif kind == QAudioFormat.SampleFormat.UInt8:
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128
    else:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 2**15
    channels = max(audio_format.channelCount(), 1)
    usable = samples.size - samples.size % channels
    return samples[:usable].reshape(-1, channels).mean(axis=1)


def resample(samples: np.ndarray, rate: int, target: int = TARGET_RATE) -> np.ndarray:
    """Linear resampling; plenty for speech going into Whisper."""
    if rate == target or samples.size == 0:
        return samples.astype(np.float32)
    duration = samples.size / rate
    positions = np.linspace(0, samples.size - 1, int(duration * target))
    return np.interp(positions, np.arange(samples.size), samples).astype(np.float32)


def level(samples: np.ndarray) -> float:
    """Loudness of a chunk (root mean square)."""
    return float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0


class SilenceWatcher:
    """Decides when an utterance is over, from the loudness of each chunk as it arrives."""

    def __init__(self) -> None:
        self.elapsed = 0.0
        self.heard_speech = False
        self._quiet_for = 0.0

    def add(self, chunk_level: float, seconds: float) -> bool:
        """Records one chunk; True when recording should stop."""
        self.elapsed += seconds
        if chunk_level >= SPEECH_LEVEL:
            self.heard_speech = True
            self._quiet_for = 0.0
        else:
            self._quiet_for += seconds
        if self.elapsed >= MAX_RECORDING_S:
            return True
        if not self.heard_speech:
            return self.elapsed >= WAIT_FOR_SPEECH_S
        return self._quiet_for >= SILENCE_TO_STOP_S


class VoiceRecorder(QObject):
    """Emits level_changed(loudness) as audio arrives, then finished(samples) with 16 kHz mono
    audio, or failed(message)."""

    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    level_changed = pyqtSignal(float)

    def __init__(self) -> None:
        super().__init__()
        self._source: QAudioSource | None = None
        self._stream: QIODevice | None = None
        self._format = QAudioFormat()
        self._chunks: list[np.ndarray] = []
        self._watcher = SilenceWatcher()

    def is_recording(self) -> bool:
        return self._source is not None

    def start(self) -> None:
        device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            self.failed.emit(NO_MICROPHONE_MESSAGE)
            return
        self._format = _recording_format(device)
        self._chunks, self._watcher = [], SilenceWatcher()
        self._source = QAudioSource(device, self._format, self)
        self._stream = self._source.start()
        if self._stream is None:
            self._source = None
            self.failed.emit(NO_MICROPHONE_MESSAGE)
            return
        self._stream.readyRead.connect(self._read)

    def stop(self) -> None:
        """Ends the recording now and hands back what was captured."""
        if self._source is None:
            return
        self._source.stop()
        self._source.deleteLater()
        self._source, self._stream = None, None
        audio = np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype=np.float32)
        self.finished.emit(resample(audio, self._format.sampleRate()))

    def _read(self) -> None:
        if self._stream is None:
            return
        chunk = to_mono_float(bytes(self._stream.readAll()), self._format)
        self._chunks.append(chunk)
        loudness = level(chunk)
        self.level_changed.emit(loudness)
        if self._watcher.add(loudness, chunk.size / max(self._format.sampleRate(), 1)):
            self.stop()


def _recording_format(device: QAudioDevice) -> QAudioFormat:
    """16 kHz mono 16-bit when the device offers it, otherwise whatever it prefers."""
    wanted = QAudioFormat()
    wanted.setSampleRate(TARGET_RATE)
    wanted.setChannelCount(1)
    wanted.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    return wanted if device.isFormatSupported(wanted) else device.preferredFormat()
