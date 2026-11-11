"""
Records one utterance from the default microphone through Qt Multimedia: starts on start(),
stops on its own a moment after the speaker goes quiet (or after a time limit, or when nothing
is said at all), or early on stop(). Hands back 16 kHz mono samples, converting from whatever
format the device actually records in. Owns capture only; transcription is core/transcriber.py's.
"""

from __future__ import annotations

import time

import numpy as np
from PyQt6.QtCore import QIODevice, QObject, QTimer, pyqtSignal
from PyQt6.QtMultimedia import QAudioDevice, QAudioFormat, QAudioSource, QMediaDevices

TARGET_RATE = 16_000
# Loudness (RMS of samples in [-1, 1]) that counts as speech rather than room noise.
SPEECH_LEVEL = 0.015
SILENCE_TO_STOP_S = 1.2
WAIT_FOR_SPEECH_S = 6.0
MAX_RECORDING_S = 30.0
# Silence detection only runs when audio arrives. If the device stops delivering anything at all
# (unplugged mid-recording, blocked by privacy settings) a watchdog ends the recording instead.
WATCHDOG_MS = 500
NO_AUDIO_TIMEOUT_S = 3.0
MIC_STOPPED_MESSAGE = "The microphone stopped sending sound. Check it's connected, then try again."
NO_MICROPHONE_MESSAGE = "No microphone was found. Plug one in, or check Settings > Privacy & security > Microphone."


_BYTES_PER_SAMPLE = {
    QAudioFormat.SampleFormat.UInt8: 1,
    QAudioFormat.SampleFormat.Int16: 2,
    QAudioFormat.SampleFormat.Int32: 4,
    QAudioFormat.SampleFormat.Float: 4,
}


def frame_bytes(audio_format: QAudioFormat) -> int:
    """Bytes in one frame: one sample for every channel."""
    return _BYTES_PER_SAMPLE.get(audio_format.sampleFormat(), 2) * max(audio_format.channelCount(), 1)


def split_frames(raw: bytes, audio_format: QAudioFormat) -> tuple[bytes, bytes]:
    """(whole frames, leftover bytes). A read can end partway through a frame; the leftover
    belongs at the front of the next read. Dropping it instead would shift every later sample
    out of alignment and turn the rest of the recording into noise."""
    usable = len(raw) - len(raw) % frame_bytes(audio_format)
    return raw[:usable], raw[usable:]


def to_mono_float(raw: bytes, audio_format: QAudioFormat) -> np.ndarray:
    """Whole frames of raw device bytes as mono float samples in [-1, 1], at the device's own
    rate. Callers pass split_frames output; a stray partial frame is ignored rather than crashing."""
    kind = audio_format.sampleFormat()
    channels = max(audio_format.channelCount(), 1)
    raw = raw[: len(raw) - len(raw) % frame_bytes(audio_format)]
    if not raw:
        return np.zeros(0, dtype=np.float32)
    if kind == QAudioFormat.SampleFormat.Float:
        samples = np.frombuffer(raw, dtype=np.float32).astype(np.float32)
    elif kind == QAudioFormat.SampleFormat.Int32:
        samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / np.float32(2**31)
    elif kind == QAudioFormat.SampleFormat.UInt8:
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - np.float32(128)) / np.float32(128)
    else:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / np.float32(2**15)
    return samples.reshape(-1, channels).mean(axis=1, dtype=np.float32)


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
        self._leftover = b""
        self._watcher = SilenceWatcher()
        self._started_at = self._last_audio_at = 0.0
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(WATCHDOG_MS)
        self._watchdog.timeout.connect(self._check_alive)

    def is_recording(self) -> bool:
        return self._source is not None

    def start(self) -> None:
        if self._source is not None:
            return
        device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            self.failed.emit(NO_MICROPHONE_MESSAGE)
            return
        self._format = _recording_format(device)
        self._chunks, self._watcher, self._leftover = [], SilenceWatcher(), b""
        self._source = QAudioSource(device, self._format, self)
        self._stream = self._source.start()
        if self._stream is None:
            self._source.deleteLater()
            self._source = None
            self.failed.emit(NO_MICROPHONE_MESSAGE)
            return
        self._stream.readyRead.connect(self._read)
        self._started_at = self._last_audio_at = time.monotonic()
        self._watchdog.start()

    def stop(self) -> None:
        """Ends the recording now and hands back what was captured.

        The device is forgotten before it's stopped: stop() can deliver one last readyRead,
        and that must not see a live recorder and finish the recording a second time."""
        stream = self._release()
        if stream is None:
            return
        self._keep(bytes(stream.readAll()))
        audio = np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype=np.float32)
        self._chunks = []
        rate = self._format.sampleRate() or TARGET_RATE
        self.finished.emit(resample(audio, rate))

    def _release(self) -> QIODevice | None:
        """Stops the device and forgets it; returns its stream (for a last read), or None when
        nothing was recording. Forgotten first, so a readyRead during stop() finds no recorder."""
        if self._source is None:
            return None
        self._watchdog.stop()
        source, self._source = self._source, None
        stream, self._stream = self._stream, None
        source.stop()
        source.deleteLater()
        return stream

    def _check_alive(self) -> None:
        """Ends a recording that no longer gets audio, or that ran past the time limit."""
        now = time.monotonic()
        if now - self._started_at >= MAX_RECORDING_S:
            self.stop()
        elif now - self._last_audio_at >= NO_AUDIO_TIMEOUT_S:
            self._release()
            self._chunks = []
            self.failed.emit(MIC_STOPPED_MESSAGE)

    def _read(self) -> None:
        if self._stream is None:
            return
        self._keep(bytes(self._stream.readAll()))

    def _keep(self, raw: bytes) -> None:
        """Stores one chunk and stops once the utterance is over."""
        if raw:
            self._last_audio_at = time.monotonic()
        frames, self._leftover = split_frames(self._leftover + raw, self._format)
        chunk = to_mono_float(frames, self._format)
        if chunk.size:
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
