"""
Discovers the apps a user can launch (Start Menu shortcuts, App Paths registry entries and
Store apps) and keeps them in a cached, fuzzy-searchable catalog. Does not launch anything —
that belongs to app_launcher.py — and only ever reads the registry, never writes to it.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import winreg
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError
from rapidfuzz import fuzz, process, utils

from config.paths import app_data_dir
from core.logger import get_logger
from models.schema import AppEntry

logger = get_logger(__name__)

SHORTCUT_SUFFIXES = frozenset({".lnk", ".url", ".appref-ms"})
START_MENU_SUBPATH = Path("Microsoft") / "Windows" / "Start Menu" / "Programs"
APP_PATHS_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
# PowerShell 5.1 writes to a pipe in the OEM code page, which mangles non-ASCII app names.
STORE_APPS_SCRIPT = "[Console]::OutputEncoding = [Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json"
STORE_APPS_COMMAND = ["powershell", "-NoProfile", "-Command", STORE_APPS_SCRIPT]
STORE_APPS_TIMEOUT_SECONDS = 15
SKIPPED_NAME_WORDS = ("uninstall", "readme", "help", "documentation", "release notes", "website")
# Lower wins when two sources expose the same name: a Start Menu shortcut is what the user
# actually sees, and App Paths entries are often helper executables with terse names.
SOURCE_PRIORITY = {"start_menu": 0, "store_app": 1, "registry": 2}

CACHE_FILE_NAME = "app_catalog.json"
CACHE_MAX_AGE = timedelta(days=7)
DEFAULT_MATCH_LIMIT = 5


def build_app_catalog() -> list[AppEntry]:
    """
    Scans every app source on this machine and returns one entry per distinct app name.

    Each source is best-effort: one that fails (no PowerShell, a locked registry hive) is
    logged and skipped so the rest of the catalog still builds. Uninstallers, readmes and
    similar non-app shortcuts are filtered out.

    Returns:
        Launchable apps sorted by name, deduplicated case-insensitively.
    """
    discovered = [*_scan_start_menu(_start_menu_dirs()), *_scan_store_apps(), *_scan_app_paths()]
    launchable = [entry for entry in discovered if _is_launchable_name(entry.name)]
    catalog = _dedupe_by_name(launchable)
    logger.info("Built app catalog", extra={"discovered": len(discovered), "apps": len(catalog)})
    return catalog


def _start_menu_dirs() -> list[Path]:
    """The per-user and all-users Start Menu Programs folders, for whichever roots are set."""
    roots = [os.environ.get("APPDATA"), os.environ.get("PROGRAMDATA")]
    return [Path(root) / START_MENU_SUBPATH for root in roots if root]


def _scan_start_menu(folders: list[Path]) -> list[AppEntry]:
    """Every shortcut under the given Start Menu folders, recursively."""
    entries: list[AppEntry] = []
    for folder in folders:
        if not folder.is_dir():
            continue
        try:
            shortcuts = [p for p in folder.rglob("*") if p.suffix.lower() in SHORTCUT_SUFFIXES]
        except OSError as e:
            logger.warning("Couldn't scan Start Menu folder", extra={"folder": str(folder), "error": str(e)})
            continue
        entries.extend(AppEntry(name=p.stem, launch_target=str(p), source="start_menu") for p in shortcuts)
    return entries


def _scan_app_paths() -> list[AppEntry]:
    """App Paths entries from the current-user and machine-wide hives."""
    entries: list[AppEntry] = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        entries.extend(_read_app_paths_hive(hive))
    return entries


def _read_app_paths_hive(hive: int) -> list[AppEntry]:
    """Reads one hive's App Paths key; a missing or unreadable key just yields nothing."""
    try:
        with winreg.OpenKey(hive, APP_PATHS_KEY, 0, winreg.KEY_READ) as root:
            subkey_count = winreg.QueryInfoKey(root)[0]
            names = [winreg.EnumKey(root, index) for index in range(subkey_count)]
            entries = [_read_app_path(root, name) for name in names]
    except OSError as e:
        logger.warning("Couldn't read App Paths registry key", extra={"hive": hive, "error": str(e)})
        return []
    return [entry for entry in entries if entry is not None]


def _read_app_path(root: winreg.HKEYType, key_name: str) -> AppEntry | None:
    """Turns one App Paths subkey into an entry, or None if it has no existing executable."""
    try:
        with winreg.OpenKey(root, key_name, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, "")
    except OSError as e:
        logger.debug("Skipped unreadable App Paths entry", extra={"key": key_name, "error": str(e)})
        return None
    target = Path(os.path.expandvars(str(value).strip().strip('"')))
    if not target.is_file():
        return None
    name = key_name[: -len(".exe")] if key_name.lower().endswith(".exe") else key_name
    return AppEntry(name=name, launch_target=str(target), source="registry")


def _scan_store_apps() -> list[AppEntry]:
    """Store/UWP apps as listed by Get-StartApps. Any failure here leaves the catalog without them."""
    try:
        result = subprocess.run(
            STORE_APPS_COMMAND,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=STORE_APPS_TIMEOUT_SECONDS,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("Couldn't list Store apps via Get-StartApps", extra={"error": str(e)})
        return []
    return _parse_start_apps(result.stdout)


def _parse_start_apps(raw_json: str) -> list[AppEntry]:
    """Parses Get-StartApps JSON, which is a bare object rather than a list when there's one app."""
    if not raw_json.strip():
        return []
    try:
        items = json.loads(raw_json)
    except json.JSONDecodeError as e:
        logger.warning("Get-StartApps returned output that isn't JSON", extra={"error": str(e)})
        return []
    if isinstance(items, dict):
        items = [items]
    return [
        AppEntry(name=item["Name"], launch_target=item["AppID"], source="store_app")
        for item in items
        if isinstance(item, dict) and item.get("Name") and item.get("AppID")
    ]


def _is_launchable_name(name: str) -> bool:
    """False for blank names and for uninstallers, readmes and other non-app shortcuts."""
    lowered = name.strip().lower()
    return bool(lowered) and not any(word in lowered for word in SKIPPED_NAME_WORDS)


def _dedupe_by_name(entries: list[AppEntry]) -> list[AppEntry]:
    """Keeps one entry per case-insensitive name, preferring the highest-priority source."""
    best: dict[str, AppEntry] = {}
    for entry in sorted(entries, key=lambda e: SOURCE_PRIORITY[e.source]):
        best.setdefault(entry.name.strip().casefold(), entry)
    return sorted(best.values(), key=lambda e: e.name.casefold())


class AppCatalog:
    """
    The app list the agent searches when asked to open something. It's built on a background
    thread at startup while the API may already be answering, so every read goes through a lock.
    """

    def __init__(self, cache_path: Path | None = None) -> None:
        self._cache_path = cache_path
        self._entries: list[AppEntry] = []
        self._is_ready = False
        self._lock = threading.Lock()

    def load_or_build(self) -> None:
        """Loads the cached catalog if it's under a week old, otherwise rescans and saves it."""
        cached = self._read_cache()
        if cached is None:
            self.refresh()
            return
        self._replace_entries(cached)
        logger.info("Loaded app catalog from cache", extra={"apps": len(cached)})

    def refresh(self) -> None:
        """Rescans the machine for apps and overwrites the cache."""
        entries = build_app_catalog()
        self._replace_entries(entries)
        self._write_cache(entries)

    def entries(self) -> list[AppEntry]:
        """A snapshot copy of the current catalog — empty until the first load finishes."""
        with self._lock:
            return list(self._entries)

    def is_ready(self) -> bool:
        """True once a load or refresh has finished at least once."""
        with self._lock:
            return self._is_ready

    def find(self, query: str, limit: int = DEFAULT_MATCH_LIMIT) -> list[tuple[AppEntry, float]]:
        """
        Fuzzy-matches query against app names.

        Args:
            query: What the user called the app, e.g. "vs code" or "spotify".
            limit: Maximum number of matches to return.

        Returns:
            (entry, score) pairs with scores from 0 to 100, best match first. Empty if the
            query is blank or the catalog hasn't loaded yet.
        """
        entries = self.entries()
        if not query.strip() or not entries or limit < 1:
            return []
        names = [entry.name for entry in entries]
        matches = process.extract(query, names, scorer=fuzz.WRatio, processor=utils.default_process, limit=limit)
        return [(entries[index], float(score)) for _, score, index in matches]

    def _replace_entries(self, entries: list[AppEntry]) -> None:
        """Swaps in a new catalog and marks it ready."""
        with self._lock:
            self._entries = list(entries)
            self._is_ready = True

    def _cache_file(self) -> Path:
        """The explicit cache path if one was given, otherwise the per-user default."""
        return self._cache_path or app_data_dir() / CACHE_FILE_NAME

    def _read_cache(self) -> list[AppEntry] | None:
        """The cached entries, or None if the cache is missing, stale or unreadable."""
        path = self._cache_file()
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            age = datetime.now(UTC) - datetime.fromisoformat(payload["built_at"])
            entries = [AppEntry.model_validate(item) for item in payload["entries"]]
        except (OSError, ValueError, KeyError, TypeError, ValidationError) as e:
            logger.warning("Ignoring unreadable app catalog cache", extra={"path": str(path), "error": str(e)})
            return None
        if age > CACHE_MAX_AGE:
            logger.info("App catalog cache is stale, rebuilding", extra={"age_days": age.days})
            return None
        return entries

    def _write_cache(self, entries: list[AppEntry]) -> None:
        """Saves the catalog; a failed write only costs a rescan next startup, so it's logged, not raised."""
        path = self._cache_file()
        payload = {"built_at": datetime.now(UTC).isoformat(), "entries": [e.model_dump() for e in entries]}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as e:
            logger.warning("Couldn't save app catalog cache", extra={"path": str(path), "error": str(e)})
