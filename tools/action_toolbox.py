"""
The tools that do something on the user's machine — open apps, files, folders, websites and
Windows settings, save notes — plus the read-only system status and note search. Every tool
that launches or writes is marked as needing the user's confirmation. Owns the tool
definitions; the actual work happens in app_launcher, system_tools and note_tools.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.exceptions import ToolError
from models.chat import ToolResult
from models.schema import AppEntry, SourceRef
from tools.app_catalog import AppCatalog
from tools.app_launcher import launch_app
from tools.file_tools import source_ref_for
from tools.note_tools import save_note, search_notes
from tools.registry import Tool, ToolRegistry, file_name_arg, object_schema, string_param, tool_spec
from tools.system_tools import (
    SETTINGS_PAGES,
    open_path,
    open_url,
    open_windows_setting,
    read_system_status,
    reveal_in_explorer,
)

MIN_APP_MATCH_SCORE = 75.0
# Start Menu shortcuts are what people actually click; prefer them on near-ties over a bare
# registry exe name like "chrome" vs "Google Chrome".
SOURCE_BONUS = {"start_menu": 3.0, "store_app": 2.0, "registry": 0.0}

_PATH_ONLY = object_schema({"path": string_param("Full path from a search result")}, ["path"])
OPEN_APP = tool_spec(
    "open_app",
    "Launch an installed app by name, e.g. 'Spotify' or 'VS Code'.",
    object_schema({"name": string_param("App name")}, ["name"]),
)
OPEN_FILE = tool_spec("open_file", "Open a file or folder in its default app.", _PATH_ONLY)
REVEAL_FILE = tool_spec("reveal_in_explorer", "Show a file selected in File Explorer.", _PATH_ONLY)
OPEN_WEBSITE = tool_spec(
    "open_website",
    "Open an http(s) URL in the default browser.",
    object_schema({"url": string_param("Full http(s) URL")}, ["url"]),
)
OPEN_SETTING = tool_spec(
    "open_windows_setting",
    f"Open a Windows Settings page. Pages: {', '.join(sorted(SETTINGS_PAGES))}.",
    object_schema({"page": string_param("Settings page name")}, ["page"]),
)
SAVE_NOTE = tool_spec(
    "save_note",
    "Save a note to Nimbus's own notes folder.",
    object_schema({"title": string_param("Short title"), "body": string_param("Note text")}, ["body"]),
)
SEARCH_NOTES = tool_spec(
    "search_notes",
    "Search the user's saved Nimbus notes.",
    object_schema({"query": string_param("Words to look for; empty lists the newest notes")}),
)
SYSTEM_STATUS = tool_spec(
    "system_status", "Battery, disk space, CPU, memory, local time and uptime.", object_schema({})
)


def best_app_match(apps: AppCatalog, name: str, min_score: float = MIN_APP_MATCH_SCORE) -> AppEntry | None:
    """The best catalog entry for name if it scores at least min_score, else None. Shared by
    the open_app tool, the fast path and the /apps/launch route so all three pick the same app."""
    hits = apps.find(name, limit=5)
    ranked = sorted(hits, key=lambda hit: hit[1] + SOURCE_BONUS[hit[0].source], reverse=True)
    if not ranked or ranked[0][1] < min_score:
        return None
    return ranked[0][0]


class ActionToolbox:
    """Builds and serves the action and system tools. path_guard rejects paths outside the
    user's shared folders, the same check the file tools use."""

    def __init__(self, app_catalog: AppCatalog, path_guard: Callable[[Path], bool]) -> None:
        self._apps = app_catalog
        self._path_guard = path_guard

    def register(self, registry: ToolRegistry) -> None:
        for tool in self._tools():
            registry.register(tool)

    def open_app(self, args: dict[str, Any]) -> ToolResult:
        """Launches the installed app that best matches the requested name."""
        entry = self.best_app_match(args["name"])
        if entry is None:
            raise ToolError(f"No installed app looks like {args['name']!r}.")
        launch_app(entry)
        return ToolResult(content=f"Opened {entry.name}.")

    def best_app_match(self, name: str, min_score: float = MIN_APP_MATCH_SCORE) -> AppEntry | None:
        """The best catalog entry for name if it scores at least min_score, else None."""
        return best_app_match(self._apps, name, min_score)

    def is_shared(self, path: Path) -> bool:
        """True if path, once resolved, is inside the user's shared folders."""
        return self._path_guard(path.expanduser().resolve())

    def open_file(self, args: dict[str, Any]) -> ToolResult:
        path = self._checked_path(args["path"])
        open_path(path)
        return ToolResult(content=f"Opened {path.name}.", sources=[source_ref_for(path)])

    def reveal_file(self, args: dict[str, Any]) -> ToolResult:
        path = self._checked_path(args["path"])
        reveal_in_explorer(path)
        return ToolResult(content=f"Showed {path.name} in File Explorer.", sources=[source_ref_for(path)])

    def open_website(self, args: dict[str, Any]) -> ToolResult:
        open_url(args["url"])
        return ToolResult(content=f"Opened {args['url']} in the browser.")

    def open_setting(self, args: dict[str, Any]) -> ToolResult:
        page = open_windows_setting(args["page"])
        return ToolResult(content=f"Opened Windows Settings → {page}.")

    def system_status(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(content=read_system_status().model_dump_json(indent=1))

    def write_note(self, args: dict[str, Any]) -> ToolResult:
        path = save_note(args.get("title", ""), args.get("body", ""))
        return ToolResult(content=f"Saved the note as {path.name}.", sources=[source_ref_for(path)])

    def find_notes(self, args: dict[str, Any]) -> ToolResult:
        """Searches saved notes; an empty query lists the newest."""
        notes = search_notes(args.get("query", ""))
        if not notes:
            return ToolResult(content="No saved notes match that.")
        lines = [f"- {n.title} ({n.modified_at:%Y-%m-%d}): {n.preview}" for n in notes]
        sources = [SourceRef(file_name=Path(n.path).name, file_path=n.path, score=1.0) for n in notes]
        return ToolResult(content="\n".join(lines), sources=sources)

    def _checked_path(self, raw: str) -> Path:
        """An existing path inside the user's shared folders, or a ToolError."""
        path = Path(raw).expanduser().resolve()
        if not self._path_guard(path):
            raise ToolError(f"{path} is outside the folders the user shared with Nimbus.")
        if not path.exists():
            raise ToolError(f"{path} doesn't exist. Use find_files_by_name to get the exact path.")
        return path

    def _tools(self) -> list[Tool]:
        """Pairs each spec with its handler. Launching or writing anything requires confirmation."""
        return [
            Tool(OPEN_APP, self.open_app, lambda a: f"Open the app “{a.get('name', '')}”", True),
            Tool(OPEN_FILE, self.open_file, lambda a: f"Open {file_name_arg(a)}", True),
            Tool(REVEAL_FILE, self.reveal_file, lambda a: f"Show {file_name_arg(a)} in File Explorer", True),
            Tool(OPEN_WEBSITE, self.open_website, lambda a: f"Open {a.get('url', '')}", True),
            Tool(OPEN_SETTING, self.open_setting, lambda a: f"Open Windows Settings → {a.get('page', '')}", True),
            Tool(
                SAVE_NOTE, self.write_note, lambda a: f"Save a note: “{a.get('title') or a.get('body', '')[:40]}”", True
            ),
            Tool(SEARCH_NOTES, self.find_notes, lambda a: "Searched notes"),
            Tool(SYSTEM_STATUS, self.system_status, lambda a: "Checked the system status"),
        ]
