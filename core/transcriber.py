"""
Turns recorded speech into text with a local Whisper model (faster-whisper, int8 on the CPU), so
voice input works offline and no audio ever leaves the PC. The model downloads once (about 150 MB
for base.en) and then loads in a second or two. Takes 16 kHz mono samples, never files, so no
audio decoder is needed. Owns transcription only; recording is the UI's job.
"""

from __future__ import annotations

import threading

import numpy as np
from faster_whisper import WhisperModel

from config.paths import model_cache_dir
from config.settings import get_settings
from core.exceptions import SpeechError
from core.logger import get_logger

logger = get_logger(__name__)

SAMPLE_RATE = 16_000
# Shorter than this is a click or a cough, not something to transcribe.
MIN_SPEECH_SECONDS = 0.3
NOTHING_HEARD_MESSAGE = "Didn't catch anything. Click the microphone and start speaking."


class Transcriber:
    """Thread-safe: load() can run in the background while the user is still speaking."""

    def __init__(self, model_name: str, threads: int) -> None:
        self._model_name = model_name
        self._threads = threads
        self._model: WhisperModel | None = None
        self._lock = threading.Lock()

    def is_ready(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        """Loads (downloading on first use) the Whisper model.

        Raises:
            SpeechError: The model couldn't be downloaded or loaded.
        """
        with self._lock:
            if self._model is not None:
                return
            try:
                logger.info("Loading speech model", extra={"model": self._model_name})
                self._model = WhisperModel(
                    self._model_name,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=self._threads,
                    download_root=str(model_cache_dir() / "whisper"),
                )
            except Exception as e:
                raise SpeechError(
                    f"Couldn't load the speech model: {e}. The first use needs internet access to download it."
                ) from e

    def transcribe(self, samples: np.ndarray) -> str:
        """The words in samples (16 kHz mono floats in [-1, 1]).

        Raises:
            SpeechError: Nothing was said, or the model failed.
        """
        if samples.size < SAMPLE_RATE * MIN_SPEECH_SECONDS:
            raise SpeechError(NOTHING_HEARD_MESSAGE)
        self.load()
        model = self._model
        if model is None:
            raise SpeechError("The speech model isn't loaded.")
        try:
            # vad_filter drops the silence before and after, and stops Whisper inventing words in it.
            segments, _ = model.transcribe(samples, language="en", beam_size=1, vad_filter=True)
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as e:
            raise SpeechError(f"Couldn't transcribe the recording: {e}") from e
        if not text:
            raise SpeechError(NOTHING_HEARD_MESSAGE)
        return text


_transcriber: Transcriber | None = None


def get_transcriber() -> Transcriber:
    """The process-wide Transcriber, built from settings on first use."""
    global _transcriber
    if _transcriber is None:
        settings = get_settings()
        _transcriber = Transcriber(settings.whisper_model, settings.embedding_threads)
    return _transcriber
