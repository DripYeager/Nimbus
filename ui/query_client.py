"""
The thin API client between the overlay and /query: fires a streamed request when the user
submits a query, and relays each SSE event back to the overlay's render methods. Owns the
HTTP/SSE plumbing only — it has no opinion on how the overlay displays what it's told.
"""

from __future__ import annotations

import threading

import httpx
from PyQt6.QtCore import QObject, pyqtSignal

from config.settings import get_settings
from core.logger import get_logger
from core.sse import parse_sse_events
from models.schema import SourceRef
from ui.overlay import OverlayWindow

logger = get_logger(__name__)

QUERY_HTTP_TIMEOUT_SECONDS = 30.0
UNREACHABLE_MESSAGE = "Couldn't reach Nimbus. Check that the app is running."


class QueryClient(QObject):
    """Streams one /query request at a time and renders its events onto an OverlayWindow."""

    _token_received = pyqtSignal(str)
    _sources_received = pyqtSignal(list)
    _failed = pyqtSignal(str)

    def __init__(self, overlay: OverlayWindow) -> None:
        super().__init__()
        self._overlay = overlay
        self._current: _StreamRequest | None = None

    def setup(self) -> None:
        """Wires the overlay's lifecycle signals and this client's own thread-bridging signals."""
        self._overlay.query_submitted.connect(self.start)
        self._overlay.dismissed.connect(self.cancel)
        self._token_received.connect(self._overlay.append_answer_token)
        self._sources_received.connect(self._overlay.set_sources)
        self._failed.connect(self._overlay.show_error)

    def start(self, text: str) -> None:
        """Cancels any in-flight request, starts the thinking state, and streams a new query."""
        self.cancel()
        self._overlay.start_thinking()
        self._current = _StreamRequest(get_settings().api_base_url, text, self)
        threading.Thread(target=self._current.run, daemon=True).start()

    def cancel(self) -> None:
        """Cancels any in-flight request so its background thread stops emitting events."""
        if self._current is not None:
            self._current.cancel()
            self._current = None


class _StreamRequest:
    """One in-flight /query call: owns the httpx stream and a cooperative cancellation flag."""

    def __init__(self, base_url: str, text: str, client: QueryClient) -> None:
        self._base_url = base_url
        self._text = text
        self._client = client
        self._cancelled = False
        self._response: httpx.Response | None = None

    def cancel(self) -> None:
        """Flags this request cancelled and closes its connection so a blocked read wakes up."""
        self._cancelled = True
        if self._response is not None:
            self._response.close()

    def run(self) -> None:
        """Streams /query on the calling (background) thread, relaying each SSE event."""
        try:
            self._stream_events()
        except (httpx.HTTPError, OSError) as e:
            if not self._cancelled:
                logger.warning("Query stream failed", extra={"error": str(e)})
                self._client._failed.emit(UNREACHABLE_MESSAGE)

    def _stream_events(self) -> None:
        """Opens the SSE connection and dispatches each frame until done or cancelled."""
        url = f"{self._base_url}/query"
        with httpx.stream("POST", url, json={"text": self._text}, timeout=QUERY_HTTP_TIMEOUT_SECONDS) as response:
            self._response = response
            response.raise_for_status()
            for event_name, data in parse_sse_events(response.iter_lines()):
                if self._cancelled:
                    return
                self._dispatch(event_name, data)

    def _dispatch(self, event_name: str, data: dict[str, object]) -> None:
        """Emits the client signal matching one parsed SSE frame."""
        if event_name == "started":
            sources = [SourceRef(**item) for item in data.get("sources", [])]
            self._client._sources_received.emit(sources)
        elif event_name == "token":
            self._client._token_received.emit(data["text"])
        elif event_name == "error":
            self._client._failed.emit(data["message"])
