"""
Starts Nimbus when the user signs in to Windows, via a shortcut in their per-user Startup
folder — no registry edits and no admin rights. Owns that shortcut only; launching the app
itself is main.py's job.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pywintypes import com_error
from win32com.client import Dispatch

from config.paths import is_frozen
from core.exceptions import AutostartError
from core.logger import get_logger

logger = get_logger(__name__)

SHORTCUT_NAME = "Nimbus.lnk"
STARTUP_SUBPATH = Path("Microsoft") / "Windows" / "Start Menu" / "Programs" / "Startup"
REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRY_SCRIPT = REPO_ROOT / "main.py"
ICON_PATH = REPO_ROOT / "assets" / "nimbus.ico"
# pythonw has no console window, so a dev install doesn't flash a terminal at sign-in.
WINDOWLESS_PYTHON = "pythonw.exe"


def _startup_dir() -> Path:
    """The current user's Startup folder."""
    roaming = os.environ.get("APPDATA")
    if not roaming:
        raise AutostartError("Can't find your Windows profile folder (APPDATA isn't set), so autostart is unavailable.")
    return Path(roaming) / STARTUP_SUBPATH


def _shortcut_path() -> Path:
    return _startup_dir() / SHORTCUT_NAME


def is_autostart_enabled() -> bool:
    """True when the Startup shortcut exists."""
    return _shortcut_path().exists()


def enable_autostart() -> None:
    """
    Creates (or refreshes) the Startup shortcut that launches Nimbus at sign-in.

    Raises:
        AutostartError: The shortcut couldn't be written.
    """
    path = _shortcut_path()
    try:
        _write_shortcut(path)
    except (OSError, com_error) as e:
        raise AutostartError(
            f"Couldn't create the startup shortcut at {path}. Check that the folder exists and isn't read-only."
        ) from e
    logger.info("Enabled autostart", extra={"shortcut": str(path)})


def disable_autostart() -> None:
    """
    Removes the Startup shortcut; does nothing when it isn't there.

    Raises:
        AutostartError: The shortcut exists but couldn't be deleted.
    """
    path = _shortcut_path()
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        raise AutostartError(f"Couldn't remove {path}. Close anything using it and try again.") from e
    logger.info("Disabled autostart", extra={"shortcut": str(path)})


def _launch_command() -> tuple[str, str]:
    """(target, arguments): the packaged exe itself, or windowless Python running main.py."""
    if is_frozen():
        return sys.executable, ""
    return str(Path(sys.executable).with_name(WINDOWLESS_PYTHON)), f'"{ENTRY_SCRIPT}"'


def _write_shortcut(path: Path) -> None:
    """Writes the .lnk through the Windows Script Host COM object."""
    target, arguments = _launch_command()
    shortcut = Dispatch("WScript.Shell").CreateShortcut(str(path))
    shortcut.TargetPath = target
    shortcut.Arguments = arguments
    shortcut.WorkingDirectory = str(Path(target).parent if is_frozen() else REPO_ROOT)
    if ICON_PATH.exists():
        shortcut.IconLocation = str(ICON_PATH)
    shortcut.Save()
