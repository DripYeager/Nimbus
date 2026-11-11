"""
File-tidying tools: move a file or folder, rename it, and undo the last change. These are the
only tools that change the user's own files, so every call waits for approval (no "always
allow"), both ends must be inside the folders the user shared, a shared folder itself can't be
moved, and nothing is deleted or overwritten. Owns those checks and the wording; the operations
and the undo log live in core/file_tidy.py.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.exceptions import ToolError
from core.file_tidy import FileChange, FileTidier
from models.chat import ToolResult
from tools.file_tools import source_ref_for
from tools.registry import Tool, ToolRegistry, file_name_arg, object_schema, string_param, tool_spec

MOVE = tool_spec(
    "move_file",
    "Move a file or folder into another folder (created if needed). Both must be in the user's shared folders. "
    "Never overwrites: a taken name gets (2).",
    object_schema(
        {"path": string_param("Full path of the file or folder"), "to_folder": string_param("Full path of the folder")},
        ["path", "to_folder"],
    ),
)
RENAME = tool_spec(
    "rename_file",
    "Rename a file or folder in place. Without an extension in the new name, the file keeps its type.",
    object_schema(
        {"path": string_param("Full path of the file or folder"), "new_name": string_param("The new name")},
        ["path", "new_name"],
    ),
)
UNDO = tool_spec("undo_file_change", "Put back the most recent move or rename.", object_schema({}))


class TidyToolbox:
    """path_guard is the shared-folders check; shared_roots are the folders themselves."""

    def __init__(
        self, tidier: FileTidier, path_guard: Callable[[Path], bool], shared_roots: Callable[[], list[Path]]
    ) -> None:
        self._tidier = tidier
        self._path_guard = path_guard
        self._shared_roots = shared_roots

    def register(self, registry: ToolRegistry) -> None:
        for spec, handler, describe, rule in (
            (MOVE, self.move, lambda a: f"Move {file_name_arg(a)} to {a.get('to_folder', '')}", self._move_allowed),
            (
                RENAME,
                self.rename,
                lambda a: f"Rename {file_name_arg(a)} to {a.get('new_name', '')}",
                self._rename_allowed,
            ),
            (UNDO, self.undo, lambda a: self.describe_undo(), None),
        ):
            tool = Tool(spec, handler, describe, requires_confirmation=True, confirm_when=rule, always_allowable=False)
            registry.register(tool)

    def move(self, args: dict[str, Any]) -> ToolResult:
        source, folder = self._move_paths(args)
        return _done(self._tidier.move(source, folder), "Moved")

    def rename(self, args: dict[str, Any]) -> ToolResult:
        return _done(self._tidier.rename(self._movable(str(args["path"])), str(args["new_name"])), "Renamed")

    def _move_allowed(self, args: dict[str, Any], user_text: str) -> bool:
        """A move the checks will refuse anyway goes straight to the refusal, with no card."""
        return _passes(lambda: self._move_paths(args))

    def _rename_allowed(self, args: dict[str, Any], user_text: str) -> bool:
        return _passes(lambda: self._movable(str(args["path"])))

    def _move_paths(self, args: dict[str, Any]) -> tuple[Path, Path]:
        source = self._movable(str(args["path"]))
        folder = Path(str(args["to_folder"])).expanduser().resolve()
        if not self._path_guard(folder):
            raise ToolError(f"{folder} isn't inside a folder the user shared, so nothing was moved there.")
        return source, folder

    def undo(self, args: dict[str, Any]) -> ToolResult:
        return _done(self._tidier.undo_last(), "Put back")

    def describe_undo(self) -> str:
        """The approval card says exactly which change will be put back."""
        last = self._tidier.last_change()
        if last is None:
            return "Undo the last file move or rename (there isn't one)"
        return f"Put {last.destination} back at {last.source}"

    def _movable(self, raw: str) -> Path:
        """An existing path inside the shared folders that isn't a shared folder itself."""
        path = Path(raw).expanduser().resolve()
        if not self._path_guard(path):
            raise ToolError(f"{path} is outside the folders the user shared with Nimbus.")
        if any(path == root.expanduser().resolve() for root in self._shared_roots()):
            raise ToolError(f"{path} is one of the shared folders itself; Nimbus doesn't move those.")
        return path


def _passes(check: Callable[[], object]) -> bool:
    """True when check doesn't refuse. Anything unexpected still asks, to stay on the safe side."""
    try:
        check()
    except ToolError:
        return False
    except Exception:
        return True
    return True


def _done(change: FileChange, verb: str) -> ToolResult:
    return ToolResult(
        content=f"{verb} {change.source} to {change.destination}.", sources=[source_ref_for(change.destination)]
    )
