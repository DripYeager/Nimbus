"""
Helps someone get a local model running without touching a terminal: finds the Ollama install,
starts it if it's installed but not running, and downloads ("pulls") a model in the background
while tracking progress. Owns setup only — chatting with the model is llm/ollama_provider.py.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

import httpx
import ollama

from config.paths import ollama_install_candidates
from core.exceptions import ProviderError
from core.logger import get_logger
from models.api import OllamaStatus

logger = get_logger(__name__)

# The tray app ships next to ollama.exe and starts the server itself; prefer it when present.
TRAY_APP_NAME = "ollama app.exe"
REACHABILITY_TIMEOUT_SECONDS = 2.0
DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
OLLAMA_ERRORS = (ollama.RequestError, ollama.ResponseError, ConnectionError, httpx.HTTPError)


def find_ollama() -> Path | None:
    """The ollama.exe to launch, or None if Ollama isn't installed."""
    on_path = shutil.which("ollama")
    if on_path:
        return Path(on_path)
    return next((path for path in ollama_install_candidates() if path.is_file()), None)


def same_model(installed: str, wanted: str) -> bool:
    """Ollama treats "qwen2.5" and "qwen2.5:latest" as one model."""

    def _tagged(name: str) -> str:
        return name if ":" in name else f"{name}:latest"

    return _tagged(installed.strip().lower()) == _tagged(wanted.strip().lower())


class OllamaSetup:
    """Status, start and pull for the configured Ollama server. One pull at a time."""

    def __init__(self, host_source: Callable[[], str]) -> None:
        # Read on every call, so changing the address in Settings takes effect immediately.
        self._host_source = host_source
        self._lock = threading.Lock()
        self._pulling: str | None = None
        self._pull_percent: float | None = None
        self._pull_error: str | None = None

    def status(self, model: str) -> OllamaStatus:
        """Is Ollama installed, is it running, and does it already have model?"""
        models = self._installed_models()
        with self._lock:
            return OllamaStatus(
                installed=models is not None or find_ollama() is not None,
                running=models is not None,
                models=models or [],
                has_model=any(same_model(name, model) for name in models or []),
                pulling=self._pulling,
                pull_percent=self._pull_percent,
                pull_error=self._pull_error,
            )

    def start(self) -> None:
        """Launches Ollama in the background, detached so it outlives Nimbus like it normally would."""
        exe = find_ollama()
        if exe is None:
            raise ProviderError("Ollama isn't installed yet. Download it from ollama.com, then try again.")
        tray_app = exe.with_name(TRAY_APP_NAME)
        command = [str(tray_app)] if tray_app.is_file() else [str(exe), "serve"]
        try:
            subprocess.Popen(command, creationflags=DETACHED, close_fds=True)
        except OSError as e:
            raise ProviderError(f"Couldn't start Ollama ({exe}): {e}") from e
        logger.info("Started Ollama", extra={"command": command[0]})

    def pull(self, model: str) -> None:
        """Starts downloading model on a background thread; progress shows up in status()."""
        with self._lock:
            if self._pulling is not None:
                raise ProviderError(f"Already downloading {self._pulling}. Wait for it to finish.")
            self._pulling, self._pull_percent, self._pull_error = model, 0.0, None
        threading.Thread(target=self._run_pull, args=(model,), name="ollama-pull", daemon=True).start()

    def _run_pull(self, model: str) -> None:
        """Streams the download, recording the overall percentage as layers arrive."""
        try:
            for update in ollama.Client(host=self._host_source()).pull(model, stream=True):
                if update.total:
                    with self._lock:
                        self._pull_percent = round(100.0 * (update.completed or 0) / update.total, 1)
            logger.info("Downloaded Ollama model", extra={"model": model})
        except OLLAMA_ERRORS as e:
            logger.warning("Ollama model download failed", extra={"model": model, "error": str(e)})
            with self._lock:
                self._pull_error = f"Couldn't download {model}: {e}"
        finally:
            with self._lock:
                self._pulling, self._pull_percent = None, None

    def _installed_models(self) -> list[str] | None:
        """Names of downloaded models, or None when the server isn't reachable."""
        try:
            listing = ollama.Client(host=self._host_source(), timeout=REACHABILITY_TIMEOUT_SECONDS).list()
        except OLLAMA_ERRORS:
            return None
        return sorted(model.model for model in listing.models if model.model)
