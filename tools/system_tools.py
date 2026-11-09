"""
Small Windows actions the agent can take on the user's behalf: open a file, folder or web page,
show a file in Explorer, jump to a Settings page, and read basic machine status. Does not
launch apps (app_launcher.py) and never changes a system setting itself — it only opens the page.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import psutil
from rapidfuzz import fuzz, process

from core.exceptions import ToolError
from core.logger import get_logger
from models.system import SystemStatus

logger = get_logger(__name__)

ALLOWED_URL_SCHEMES = frozenset({"http", "https"})
BYTES_PER_GB = 1024**3
SECONDS_PER_HOUR = 3600
SETTING_MATCH_CUTOFF = 80
# Words people tack on ("bluetooth settings", "display page") that carry no meaning for matching.
SETTING_FILLER_WORDS = re.compile(r"\b(settings?|page|menu|options?)\b")
SETTING_SEPARATORS = re.compile(r"[\s_\-]+")

SETTINGS_PAGES: dict[str, str] = {
    "wifi": "ms-settings:network-wifi",
    "bluetooth": "ms-settings:bluetooth",
    "display": "ms-settings:display",
    "sound": "ms-settings:sound",
    "notifications": "ms-settings:notifications",
    "power": "ms-settings:powersleep",
    "battery": "ms-settings:batterysaver",
    "storage": "ms-settings:storagesense",
    "apps": "ms-settings:appsfeatures",
    "default-apps": "ms-settings:defaultapps",
    "network": "ms-settings:network-status",
    "vpn": "ms-settings:network-vpn",
    "windows-update": "ms-settings:windowsupdate",
    "privacy": "ms-settings:privacy",
    "mouse": "ms-settings:mousetouchpad",
    "keyboard": "ms-settings:keyboard",
    "personalization": "ms-settings:personalization",
    "background": "ms-settings:personalization-background",
    "themes": "ms-settings:themes",
    "date-time": "ms-settings:dateandtime",
    "language": "ms-settings:regionlanguage",
    "accounts": "ms-settings:yourinfo",
    "focus": "ms-settings:quiethours",
    "do-not-disturb": "ms-settings:quiethours",
    "printers": "ms-settings:printers",
    "about": "ms-settings:about",
}


def open_path(path: Path) -> None:
    """
    Opens a file in its default app, or a folder in Explorer.

    Raises:
        ToolError: If the path doesn't exist or Windows has nothing registered to open it.
    """
    target = _require_existing(path)
    try:
        os.startfile(target)
    except OSError as e:
        raise ToolError(f"Couldn't open {target}: {e}. Check that an app is associated with this file type.") from e
    logger.info("Opened path", extra={"path": str(target)})


def reveal_in_explorer(path: Path) -> None:
    """
    Opens an Explorer window on the folder containing path, with the item selected.

    Raises:
        ToolError: If the path doesn't exist or Explorer couldn't be started.
    """
    target = _require_existing(path)
    try:
        # explorer.exe parses its own command line non-standardly, so the path is quoted by
        # hand here rather than left to subprocess's list-argument quoting.
        subprocess.Popen(f'explorer.exe /select,"{target}"')
    except OSError as e:
        raise ToolError(f"Couldn't open Explorer to show {target}: {e}") from e
    logger.info("Revealed path in Explorer", extra={"path": str(target)})


def open_url(url: str) -> None:
    """
    Opens an http(s) link in the default browser.

    Raises:
        ToolError: If the URL isn't a well-formed http/https link or no browser could be started.
    """
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES or not parsed.netloc:
        raise ToolError(f"Refusing to open {url!r}: only http:// and https:// links with a host are allowed.")
    if not webbrowser.open(parsed.geturl()):
        raise ToolError(f"No web browser could be started to open {url}. Check the default browser setting.")
    logger.info("Opened URL", extra={"host": parsed.netloc})


def open_windows_setting(page: str) -> str:
    """
    Opens a Windows Settings page by a loose, human name like "Bluetooth settings" or "wi-fi".

    Only pages in SETTINGS_PAGES can be opened, so the model can't be talked into launching
    an arbitrary ms-settings: or other URI.

    Returns:
        The SETTINGS_PAGES key that was opened.

    Raises:
        ToolError: If nothing matches closely enough, listing the valid page names.
    """
    key = _match_setting_page(page)
    if key is None:
        valid = ", ".join(SETTINGS_PAGES)
        raise ToolError(f"No Settings page matches {page!r}. Valid pages: {valid}.")
    try:
        os.startfile(SETTINGS_PAGES[key])
    except OSError as e:
        raise ToolError(f"Windows couldn't open the {key} Settings page: {e}") from e
    logger.info("Opened Settings page", extra={"page": key})
    return key


def read_system_status() -> SystemStatus:
    """
    Takes a quick snapshot of battery, disk, CPU, memory, clock and uptime.

    CPU is sampled without blocking, so the first call in a process can read 0.0.

    Raises:
        ToolError: If psutil couldn't read the machine's counters.
    """
    try:
        battery = psutil.sensors_battery()
        disk = psutil.disk_usage(Path.home().anchor)
        cpu_percent = psutil.cpu_percent(interval=None)
        memory_percent = psutil.virtual_memory().percent
        uptime_seconds = time.time() - psutil.boot_time()
    except (OSError, psutil.Error) as e:
        raise ToolError(f"Couldn't read system status: {e}") from e
    return SystemStatus(
        battery_percent=battery.percent if battery else None,
        is_plugged_in=battery.power_plugged if battery else None,
        disk_free_gb=round(disk.free / BYTES_PER_GB, 1),
        disk_total_gb=round(disk.total / BYTES_PER_GB, 1),
        cpu_percent=cpu_percent,
        memory_percent=memory_percent,
        local_time=datetime.now().astimezone().isoformat(timespec="seconds"),
        uptime_hours=round(uptime_seconds / SECONDS_PER_HOUR, 1),
    )


def _require_existing(path: Path) -> Path:
    """Expands ~ and fails with a clear message if nothing is at the path."""
    target = path.expanduser()
    if not target.exists():
        raise ToolError(f"Nothing exists at {target}. Check the path, or search for the file first.")
    return target


def _compact_setting_name(name: str) -> str:
    """Lowercases and drops filler words and separators, so "Wi-Fi settings" becomes "wifi"."""
    without_filler = SETTING_FILLER_WORDS.sub(" ", name.lower())
    return SETTING_SEPARATORS.sub("", without_filler)


def _match_setting_page(page: str) -> str | None:
    """The SETTINGS_PAGES key for page — exact after normalizing, else the best fuzzy match."""
    wanted = _compact_setting_name(page)
    if not wanted:
        return None
    compact_keys = {_compact_setting_name(key): key for key in SETTINGS_PAGES}
    if wanted in compact_keys:
        return compact_keys[wanted]
    best = process.extractOne(wanted, list(compact_keys), scorer=fuzz.WRatio, score_cutoff=SETTING_MATCH_CUTOFF)
    return compact_keys[best[0]] if best else None
