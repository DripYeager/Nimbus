"""
Launches an app picked from the app catalog. Does not discover or match apps — that's
app_catalog.py — and never elevates: everything starts with the user's own rights.
"""

from __future__ import annotations

import os
import subprocess

from core.exceptions import AppLaunchError
from core.logger import get_logger
from models.schema import AppEntry

logger = get_logger(__name__)

STORE_APP_SHELL_PREFIX = "shell:AppsFolder\\"


def launch_app(entry: AppEntry) -> None:
    """
    Starts the app the same way double-clicking it in the Start Menu would.

    Shortcuts and executables go through the shell's default open action; Store apps are
    activated by their AppID through the AppsFolder shell namespace.

    Raises:
        AppLaunchError: If Windows refused to start it, usually because it was uninstalled or moved.
    """
    try:
        if entry.source == "store_app":
            subprocess.Popen(["explorer.exe", f"{STORE_APP_SHELL_PREFIX}{entry.launch_target}"])
        else:
            os.startfile(entry.launch_target)
    except OSError as e:
        raise AppLaunchError(
            f"Couldn't launch {entry.name} from {entry.launch_target}: {e}. "
            "It may have been uninstalled or moved — refresh the app catalog and try again."
        ) from e
    logger.info("Launched app", extra={"app": entry.name, "source": entry.source})
