"""
Runs a blocking call (an API request, a provider test) off the GUI thread and delivers the
result, or the error message, back on the GUI thread. Short calls use Qt's thread pool; long
ones that mustn't hold up quitting (a model download) use a daemon thread instead, because Qt
waits for its pool to drain before the app can exit. Owns thread hand-off only.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from core.exceptions import NimbusError
from core.logger import get_logger

logger = get_logger(__name__)


class _Signals(QObject):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)


class _CallRunnable(QRunnable):
    """Runs one function and reports through its signals."""

    def __init__(self, function: Callable[[], Any], signals: _Signals) -> None:
        super().__init__()
        self._function = function
        self._signals = signals

    def run(self) -> None:
        try:
            result = self._function()
        except NimbusError as e:
            self._signals.failed.emit(str(e))
            return
        except Exception as e:
            logger.exception("Background call crashed")
            self._signals.failed.emit(f"Unexpected error: {e}")
            return
        self._signals.succeeded.emit(result)


# Keeps each in-flight call's signal object alive until it has reported back.
_in_flight: set[_Signals] = set()


def run_in_background(
    function: Callable[[], Any],
    on_success: Callable[[Any], None],
    on_error: Callable[[str], None] | None = None,
    daemon: bool = False,
) -> None:
    """Runs function off the GUI thread, then calls on_success(result) or on_error(message)
    back on the GUI thread. daemon=True never delays quitting: the call is simply abandoned."""
    signals = _Signals()
    _in_flight.add(signals)
    signals.succeeded.connect(on_success)
    if on_error is not None:
        signals.failed.connect(on_error)
    signals.succeeded.connect(lambda _: _in_flight.discard(signals))
    signals.failed.connect(lambda _: _in_flight.discard(signals))
    runnable = _CallRunnable(function, signals)
    if daemon:
        threading.Thread(target=runnable.run, name="background-call", daemon=True).start()
    else:
        QThreadPool.globalInstance().start(runnable)
