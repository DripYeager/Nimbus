"""
Streams one chat request (a new message, or the answer to a confirmation card) from the local
API and re-emits each SSE event as a Qt signal on the GUI thread. Owns HTTP/SSE plumbing and
cancellation only — it has no opinion on how events are displayed.
"""

from __future__ import annotations

import itertools
import threading
from typing import Any

import httpx
from PyQt6.QtCore import QObject, pyqtSignal

from config.settings import get_settings
from core.logger import get_logger
from core.sse import parse_sse_events

logger = get_logger(__name__)

CONNECT_TIMEOUT_SECONDS = 5.0
UNREACHABLE_MESSAGE = "Couldn't reach Nimbus's engine. Try restarting Nimbus from the tray."


class ChatStream(QObject):
    """One request at a time; starting a new one cancels the previous. Each request carries an
    id, and anything a cancelled request had already queued for the GUI thread is dropped —
    otherwise a stale token could land in the next reply."""

    event_received = pyqtSignal(str, dict)
    failed = pyqtSignal(str)
    finished = pyqtSignal()
    _relay_event = pyqtSignal(int, str, dict)
    _relay_failed = pyqtSignal(int, str)
    _relay_finished = pyqtSignal(int)

    def __init__(self) -> None:
        super().__init__()
        self._current: _StreamRequest | None = None
        self._request_ids = itertools.count(1)
        self._relay_event.connect(self._deliver_event)
        self._relay_failed.connect(self._deliver_failed)
        self._relay_finished.connect(self._deliver_finished)

    def send(self, text: str, conversation_id: str | None) -> None:
        """Streams the reply to a new message."""
        self._start("/chat", {"text": text, "conversation_id": conversation_id})

    def answer_confirmation(self, conversation_id: str, decision: dict[str, Any]) -> None:
        """Streams the rest of a turn after the user approved or declined an action."""
        self._start(f"/chat/{conversation_id}/confirm", decision)

    def cancel(self) -> None:
        if self._current is not None:
            self._current.cancel()
            self._current = None

    def _start(self, path: str, body: dict[str, Any]) -> None:
        self.cancel()
        self._current = _StreamRequest(f"{get_settings().api_base_url}{path}", body, self, next(self._request_ids))
        threading.Thread(target=self._current.run, name="chat-stream", daemon=True).start()

    def _is_current(self, request_id: int) -> bool:
        return self._current is not None and self._current.request_id == request_id

    def _deliver_event(self, request_id: int, name: str, data: dict) -> None:
        if self._is_current(request_id):
            self.event_received.emit(name, data)

    def _deliver_failed(self, request_id: int, message: str) -> None:
        if self._is_current(request_id):
            self.failed.emit(message)

    def _deliver_finished(self, request_id: int) -> None:
        if self._is_current(request_id):
            self.finished.emit()


class _StreamRequest:
    """One in-flight request with a cooperative cancel flag."""

    def __init__(self, url: str, body: dict[str, Any], owner: ChatStream, request_id: int) -> None:
        self._url = url
        self._body = body
        self._owner = owner
        self.request_id = request_id
        self._cancelled = False
        self._response: httpx.Response | None = None

    def cancel(self) -> None:
        """Flags the request cancelled and closes the connection so a blocked read wakes up."""
        self._cancelled = True
        if self._response is not None:
            self._response.close()

    def run(self) -> None:
        """Runs on a background thread; signals cross back to the GUI thread automatically."""
        try:
            self._stream()
        except (httpx.HTTPError, httpx.StreamError, OSError, ValueError) as e:
            # ValueError covers a malformed SSE data line; StreamError a read racing a cancel.
            if not self._cancelled:
                logger.warning("Chat stream failed", extra={"error": str(e)})
                self._owner._relay_failed.emit(self.request_id, _message_for(e))
        finally:
            if not self._cancelled:
                self._owner._relay_finished.emit(self.request_id)

    def _stream(self) -> None:
        """Opens the SSE connection and relays each event until done or cancelled."""
        timeout = httpx.Timeout(get_settings().thinking_timeout_seconds, connect=CONNECT_TIMEOUT_SECONDS)
        with httpx.stream("POST", self._url, json=self._body, timeout=timeout) as response:
            self._response = response
            if response.is_error:
                response.read()
                raise _EngineError(_api_error_text(response))
            for name, data in parse_sse_events(response.iter_lines()):
                if self._cancelled:
                    return
                self._owner._relay_event.emit(self.request_id, name, data)


class _EngineError(httpx.HTTPError):
    """The engine answered, but with an error status; carries its own message for the user."""


def _api_error_text(response: httpx.Response) -> str:
    """The engine's own error message, if its body has one."""
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and (body.get("error") or body.get("detail")):
        return str(body.get("error") or body.get("detail"))
    return f"Nimbus's engine returned an error ({response.status_code})."


def _message_for(error: Exception) -> str:
    """A friendly line for the most common failures."""
    if isinstance(error, httpx.ReadTimeout):
        return "The model took too long to answer. A smaller model or a cloud provider may be faster."
    if isinstance(error, _EngineError):
        return str(error)
    if isinstance(error, ValueError):
        return "Nimbus's engine sent a reply that couldn't be read. Details are in the log file."
    return UNREACHABLE_MESSAGE
