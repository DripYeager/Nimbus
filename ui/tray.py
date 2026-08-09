"""
The pystray system tray icon and its right-click menu: pause/resume indexing, rebuild the
index, open the settings file, and quit. Talks to the API over HTTP like any other client —
it owns background-control UI only, no engine logic.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import httpx
import pystray
from PIL import Image

from config.settings import get_settings
from core.logger import get_logger
from models.schema import IndexStatus

logger = get_logger(__name__)

TRAY_ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "tray_icon.png"
TRAY_TOOLTIP = "Nimbus"
TRAY_HTTP_TIMEOUT_SECONDS = 10.0
UNREACHABLE_MESSAGE = "Couldn't reach Nimbus. Check that the app is running."
SETTINGS_FILE_NAME = ".env"
SETTINGS_TEMPLATE_FILE_NAME = ".env.example"


class TrayIcon:
    """The pystray icon and menu: pause/resume indexing, rebuild, open settings, quit."""

    def __init__(self, on_quit: Callable[[], None] | None = None) -> None:
        self._on_quit = on_quit
        self._is_paused = False
        self._icon: pystray.Icon | None = None

    def setup(self) -> None:
        """Builds the pystray icon and its menu; call run() afterward to display it."""
        self._icon = pystray.Icon("Nimbus", _load_icon_image(), TRAY_TOOLTIP, self._build_menu())

    def run(self) -> None:
        """Shows the tray icon and blocks until stop() is called — must run on the main thread."""
        self._icon.run()

    def stop(self) -> None:
        """Hides the tray icon and unblocks run()."""
        self._icon.stop()

    def _build_menu(self) -> pystray.Menu:
        """Builds the right-click menu: pause/resume, rebuild, open settings, quit."""
        return pystray.Menu(
            pystray.MenuItem(self._pause_resume_label, self._toggle_pause),
            pystray.MenuItem("Rebuild Index", self._rebuild_index),
            pystray.MenuItem("Open Settings", self._open_settings),
            pystray.MenuItem("Quit", self._quit),
        )

    def _pause_resume_label(self, _item: pystray.MenuItem) -> str:
        """Reflects the last known pause state in the menu item's own text."""
        return "Resume Indexing" if self._is_paused else "Pause Indexing"

    def _toggle_pause(self, icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        """Calls /index/pause or /index/resume for the current state, then refreshes the menu."""
        endpoint = "/index/resume" if self._is_paused else "/index/pause"
        status = _post_for_status(endpoint)
        if status is None:
            _notify_safely(icon, UNREACHABLE_MESSAGE)
            return
        self._is_paused = status.is_paused
        icon.update_menu()

    def _rebuild_index(self, icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        """Triggers a full reindex in the background via the existing /index/rebuild endpoint."""
        url = f"{get_settings().api_base_url}/index/rebuild"
        try:
            httpx.post(url, json={}, timeout=TRAY_HTTP_TIMEOUT_SECONDS)
        except httpx.HTTPError as e:
            logger.warning("Rebuild request failed", extra={"error": str(e)})
            _notify_safely(icon, UNREACHABLE_MESSAGE)

    def _open_settings(self, icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        """Opens .env (or its template, on a fresh clone) in its OS-registered default app."""
        path = _settings_file_path()
        try:
            os.startfile(path)
        except OSError as e:
            logger.warning("Couldn't open settings file", extra={"path": str(path), "error": str(e)})
            _notify_safely(icon, f"Couldn't open {path.name}: {e}")

    def _quit(self, icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        """Stops the tray icon and runs the caller-supplied shutdown hook, if any."""
        icon.stop()
        if self._on_quit is not None:
            self._on_quit()


def _post_for_status(endpoint: str) -> IndexStatus | None:
    """POSTs to an /index/* control endpoint and parses its IndexStatus, or None if unreachable."""
    url = f"{get_settings().api_base_url}{endpoint}"
    try:
        response = httpx.post(url, timeout=TRAY_HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("Index control request failed", extra={"endpoint": endpoint, "error": str(e)})
        return None
    return IndexStatus(**response.json())


def _notify_safely(icon: pystray.Icon, message: str) -> None:
    """Shows a tray notification, tolerating backends that don't support one."""
    try:
        icon.notify(message)
    except (NotImplementedError, OSError) as e:
        logger.warning("Tray notification failed", extra={"error": str(e)})


def _settings_file_path() -> Path:
    """Prefers the real .env; falls back to the documented template on a fresh, unconfigured clone."""
    repo_root = Path(__file__).resolve().parent.parent
    env_path = repo_root / SETTINGS_FILE_NAME
    return env_path if env_path.exists() else repo_root / SETTINGS_TEMPLATE_FILE_NAME


def _load_icon_image() -> Image.Image:
    """Loads the tray icon PNG — the one real image asset in the app; everything else is code-drawn."""
    return Image.open(TRAY_ICON_PATH)
