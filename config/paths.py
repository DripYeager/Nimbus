"""
Resolves where Nimbus keeps its per-user data on disk: the index, the file catalog, chats,
notes, logs, the model cache, and the user's saved settings. Does not create anything or read
any setting values — it only answers "where does this live?".
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "Nimbus"
# Lets tests and side-by-side dev installs point Nimbus at a throwaway data folder.
HOME_OVERRIDE_ENV = "NIMBUS_HOME"


def app_data_dir() -> Path:
    """The per-user data folder — %APPDATA%\\Nimbus on Windows, ~/.nimbus elsewhere. Always
    user-writable, so nothing here ever needs admin rights."""
    override = os.environ.get(HOME_OVERRIDE_ENV)
    if override:
        return Path(override).expanduser()
    roaming = os.environ.get("APPDATA")
    if sys.platform == "win32" and roaming:
        return Path(roaming) / APP_DIR_NAME
    return Path.home() / ".nimbus"


def user_settings_path() -> Path:
    """The JSON file the Settings window writes to."""
    return app_data_dir() / "settings.json"


def log_dir() -> Path:
    return app_data_dir() / "logs"


def notes_dir() -> Path:
    return app_data_dir() / "notes"


def model_cache_dir() -> Path:
    return app_data_dir() / "models"


def is_frozen() -> bool:
    """True when running from a packaged executable rather than from source."""
    return bool(getattr(sys, "frozen", False))


def asset_path(*parts: str) -> Path:
    """A file under assets/ — next to the source tree when running from source, or inside the
    unpacked bundle when running as a packaged executable."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base.joinpath("assets", *parts)
