"""
Boots and supervises the whole process: the Qt application, the engine services, the local
API server on its own thread, and the desktop UI, then shuts them all down cleanly on Quit.
Owns process lifecycle only; what each piece does lives in its own module.
"""

from __future__ import annotations

import ctypes
import sys
import threading
import time

import uvicorn
from PyQt6.QtWidgets import QApplication, QMessageBox

import api.server as server_module
from config.paths import user_settings_path
from config.settings import get_settings
from core.exceptions import StartupError
from core.launch_args import ask_path_from
from core.logger import get_logger, log_file_path
from core.service_container import AppServices
from ui.api_client import ApiClient
from ui.desktop_shell import DesktopShell
from ui.single_instance import notify_running_instance
from ui.theme.fonts import load_bundled_fonts
from ui.theme.icons import app_icon
from ui.theme.stylesheet import build_stylesheet

logger = get_logger(__name__)

SERVER_START_TIMEOUT_SECONDS = 15.0
SERVER_POLL_SECONDS = 0.05
SERVER_JOIN_TIMEOUT_SECONDS = 5.0
STARTUP_FAILED_EXIT_CODE = 1
# Lets Windows group the taskbar/tray entries under Nimbus's own icon instead of Python's.
APP_USER_MODEL_ID = "Nimbus.DesktopAssistant"


class AppRuntime:
    """Starts everything in order, blocks on the Qt event loop, and tears down on quit."""

    def __init__(self) -> None:
        self._qt_app: QApplication | None = None
        self._services: AppServices | None = None
        self._server: uvicorn.Server | None = None
        self._server_thread: threading.Thread | None = None
        self._shell: DesktopShell | None = None

    def start(self) -> int:
        """Runs Nimbus until Quit; returns the process exit code."""
        self._qt_app = _build_qt_app()
        ask_path = ask_path_from(sys.argv)
        if notify_running_instance(ask_path):
            logger.info("Nimbus is already running; asked it to show itself")
            return 0
        try:
            self._start_engine_and_ui()
            if ask_path is not None and self._shell is not None:
                self._shell.ask_about_file(ask_path)
        except Exception as e:
            # Don't leave the API thread, the watcher or the hotkey running behind a dead process,
            # and say why, a windowed build has no console, so it would otherwise just vanish.
            logger.exception("Nimbus failed to start")
            self.shutdown()
            _show_startup_error(e)
            return STARTUP_FAILED_EXIT_CODE
        logger.info("Nimbus started", extra={"port": get_settings().api_port})
        return self._qt_app.exec()

    def _start_engine_and_ui(self) -> None:
        """Engine first, then the API that serves it, then the UI that talks to the API."""
        self._services = AppServices.build()
        server_module.app.state.services = self._services
        self._start_server()
        self._services.start()
        self._shell = DesktopShell(ApiClient(), on_quit=self.shutdown)
        self._services.add_settings_listener(self._shell.settings_changed.emit)
        self._shell.start()

    def shutdown(self) -> None:
        """Stops the UI, the API server and the engine, then ends the event loop."""
        logger.info("Shutting down")
        if self._shell is not None:
            self._shell.stop()
        if self._server is not None:
            self._server.should_exit = True
        if self._server_thread is not None:
            self._server_thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
        if self._services is not None:
            self._services.stop()
        if self._qt_app is not None:
            self._qt_app.quit()

    def _start_server(self) -> None:
        """Serves the API on 127.0.0.1 only, on a background thread, and waits until it's up
        so the UI's first requests don't race it."""
        # log_config=None routes uvicorn through our own logging; its default config writes to a
        # console, which a windowed build doesn't have.
        config = uvicorn.Config(
            server_module.app, host="127.0.0.1", port=get_settings().api_port, log_level="warning", log_config=None
        )
        self._server = uvicorn.Server(config)
        self._server_thread = threading.Thread(target=self._server.run, name="api-server", daemon=True)
        self._server_thread.start()
        deadline = time.monotonic() + SERVER_START_TIMEOUT_SECONDS
        while not self._server.started and self._server_thread.is_alive() and time.monotonic() < deadline:
            time.sleep(SERVER_POLL_SECONDS)
        if not self._server.started:
            # Every window talks to the engine through this API, so running on without it would
            # only show a UI where nothing works.
            port = get_settings().api_port
            raise StartupError(
                f"Nimbus's engine couldn't start on port {port}. Another program may be using it; "
                f'set "api_port" in {user_settings_path()} or close that program, then start Nimbus again.'
            )


def _show_startup_error(error: Exception) -> None:
    """Tells the user why Nimbus closed, with the log location for anything unexpected."""
    if isinstance(error, StartupError):
        message = str(error)
    else:
        # Some exceptions carry no message; the class name is still better than a blank.
        reason = str(error) or type(error).__name__
        message = f"Nimbus couldn't start: {reason}\n\nDetails are in {log_file_path()}."
    QMessageBox.critical(None, "Nimbus", message)


def _build_qt_app() -> QApplication:
    """The Qt application: styled, iconned, and kept alive with no windows open (tray app)."""
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Nimbus")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())
    load_bundled_fonts()
    app.setStyleSheet(build_stylesheet())
    return app
