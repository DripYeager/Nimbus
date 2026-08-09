"""
Boots and supervises every Nimbus subsystem: the API server, the file watcher, the global
hotkey, the overlay, and the tray icon — each on its own thread except the overlay/tray, which
share the Qt main thread's event loop. Owns process lifecycle only; it composes the other
modules rather than implementing any of their logic itself.
"""

from __future__ import annotations

import threading

import uvicorn
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

import api.server as server_module
from config.settings import get_settings
from core.embedder import get_embedder
from core.file_watcher import FileWatcher, IndexingState
from core.indexer import Indexer
from core.logger import get_logger
from core.query_engine import QueryEngine
from core.retriever import Retriever
from core.vector_store import VectorStore
from llm.provider import get_provider
from ui.hotkey import HotkeyListener
from ui.overlay import OverlayWindow
from ui.query_client import QueryClient
from ui.tray import TrayIcon

logger = get_logger(__name__)

SERVER_JOIN_TIMEOUT_SECONDS = 5.0


class AppRuntime(QObject):
    """Builds and starts every subsystem, then blocks the main thread on the Qt event loop
    until Quit is chosen from the tray."""

    _shutdown_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._qt_app: QApplication | None = None
        self._server: uvicorn.Server | None = None
        self._server_thread: threading.Thread | None = None
        self._file_watcher: FileWatcher | None = None
        self._hotkey: HotkeyListener | None = None
        self._overlay: OverlayWindow | None = None
        self._query_client: QueryClient | None = None
        self._tray: TrayIcon | None = None

    def start(self) -> int:
        """Builds every subsystem, starts each on its own thread, and blocks on the Qt event
        loop until quit is requested — returns the process exit code."""
        self._qt_app = QApplication.instance() or QApplication([])
        self._shutdown_requested.connect(self._qt_app.quit)

        store, indexer, indexing_state = _build_indexing_resources()
        self._wire_api_state(store, indexer, indexing_state)
        self._start_uvicorn()

        self._file_watcher = FileWatcher(indexer, store, indexing_state)
        self._file_watcher.setup()
        self._file_watcher.start()
        _run_initial_index_in_background(indexer, indexing_state)

        self._start_overlay_and_hotkey()
        self._start_tray()

        return self._qt_app.exec()

    def _wire_api_state(self, store: VectorStore, indexer: Indexer, indexing_state: IndexingState) -> None:
        """Pre-populates the FastAPI app's state so its own lifespan reuses these exact
        instances instead of opening a second, independent VectorStore connection."""
        embedder = get_embedder()
        provider = get_provider(get_settings())
        server_module.app.state.store = store
        server_module.app.state.indexer = indexer
        server_module.app.state.query_engine = QueryEngine(Retriever(store, embedder), provider, store)
        server_module.app.state.indexing_state = indexing_state

    def _start_uvicorn(self) -> None:
        """Starts uvicorn bound to 127.0.0.1 on its own background thread — never 0.0.0.0."""
        config = uvicorn.Config(server_module.app, host="127.0.0.1", port=get_settings().api_port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._server_thread = threading.Thread(target=self._server.run, daemon=True)
        self._server_thread.start()

    def _start_overlay_and_hotkey(self) -> None:
        """Builds the overlay and its API client, then the hotkey that summons it. All three
        must stay referenced for the app's lifetime, or Qt would tear down their connections."""
        self._overlay = OverlayWindow()
        self._overlay.setup()
        self._query_client = QueryClient(self._overlay)
        self._query_client.setup()
        self._hotkey = HotkeyListener(get_settings().hotkey)
        self._hotkey.summoned.connect(self._overlay.summon)
        self._hotkey.start()

    def _start_tray(self) -> None:
        """Shows the tray icon via run_detached() — Qt already owns the main thread's event
        loop, so the tray can't also block it the way its own run() requires."""
        self._tray = TrayIcon(on_quit=self._request_shutdown)
        self._tray.setup()
        self._tray.run_detached()

    def _request_shutdown(self) -> None:
        """Runs on the tray's own thread when Quit is chosen: stops every subsystem, waits for
        each background thread to actually finish, then asks the Qt event loop to quit."""
        if self._server is not None:
            self._server.should_exit = True
        if self._file_watcher is not None:
            self._file_watcher.stop()
        if self._hotkey is not None:
            self._hotkey.stop()
        if self._server_thread is not None:
            self._server_thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
        self._shutdown_requested.emit()


def _build_indexing_resources() -> tuple[VectorStore, Indexer, IndexingState]:
    """Builds the store/indexer/state shared between the API, the watcher, and the initial pass."""
    store = VectorStore()
    store.connect()
    indexer = Indexer(store, get_embedder())
    return store, indexer, IndexingState()


def _run_initial_index_in_background(indexer: Indexer, indexing_state: IndexingState) -> None:
    """Indexes every watched directory once at startup, seeding indexing_state from the result
    — runs on its own thread so a large folder never delays the app becoming usable."""

    def _run() -> None:
        for directory in get_settings().watched_dirs:
            if not directory.is_dir():
                continue
            indexer.index_directory(directory)
            indexing_state.seed(str(p) for p in directory.rglob("*") if p.is_file())
        logger.info("Initial index pass complete", extra={"indexed_files": indexing_state.indexed_files})

    threading.Thread(target=_run, daemon=True).start()
