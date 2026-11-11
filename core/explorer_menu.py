r"""
Adds "Ask Nimbus about this" to File Explorer's right-click menu for every file. It's a
per-user registry entry (HKEY_CURRENT_USER\Software\Classes\*\shell), so no admin rights are
needed, and it runs Nimbus with --ask and the file's path; a running Nimbus picks that up.
On Windows 11 the entry sits under "Show more options". Owns that registry entry only.
"""

from __future__ import annotations

import winreg

from config.paths import asset_path, is_frozen
from core.autostart import launch_command
from core.exceptions import ExplorerMenuError
from core.launch_args import ASK_FLAG
from core.logger import get_logger

logger = get_logger(__name__)

VERB_KEY = r"Software\Classes\*\shell\NimbusAsk"
COMMAND_KEY = VERB_KEY + r"\command"
MENU_TEXT = "Ask Nimbus about this"


def explorer_command() -> str:
    """The command line Explorer runs, with %1 standing for the clicked file."""
    target, arguments = launch_command()
    return " ".join(part for part in (f'"{target}"', arguments, ASK_FLAG, '"%1"') if part)


def is_explorer_menu_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, COMMAND_KEY):
            return True
    except OSError:
        return False


def enable_explorer_menu() -> None:
    """
    Adds (or refreshes) the right-click entry.

    Raises:
        ExplorerMenuError: Windows refused the registry write.
    """
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, VERB_KEY) as verb:
            winreg.SetValueEx(verb, "MUIVerb", 0, winreg.REG_SZ, MENU_TEXT)
            winreg.SetValueEx(verb, "Icon", 0, winreg.REG_SZ, _icon())
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, COMMAND_KEY) as command:
            winreg.SetValueEx(command, "", 0, winreg.REG_SZ, explorer_command())
    except OSError as e:
        raise ExplorerMenuError(f"Couldn't add Nimbus to File Explorer's menu: {e}") from e
    logger.info("Added the File Explorer menu entry")


def disable_explorer_menu() -> None:
    """
    Removes the right-click entry; does nothing when it isn't there.

    Raises:
        ExplorerMenuError: The entry exists but couldn't be removed.
    """
    for key in (COMMAND_KEY, VERB_KEY):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except FileNotFoundError:
            continue
        except OSError as e:
            raise ExplorerMenuError(f"Couldn't remove Nimbus from File Explorer's menu: {e}") from e
    logger.info("Removed the File Explorer menu entry")


def _icon() -> str:
    """The packaged exe carries the icon; a source checkout points at the .ico file."""
    target, _ = launch_command()
    return target if is_frozen() else str(asset_path("nimbus.ico"))
