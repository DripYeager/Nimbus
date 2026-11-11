"""
Moves and renames the user's files when they ask, and can put the last change back. Nothing is
ever overwritten (a name that's taken gets " (2)", and the move itself is one Windows refuses
to do over an existing file), a renamed file keeps its type unless a new one is given, and every
change is appended to a log, so it can be undone even after a restart. A move whose log entry
can't be written is reversed, so there's never a change undo doesn't know about. Owns the file
operations and the log; which folders are allowed is the tools' check.
"""

from __future__ import annotations

import errno
import json
import os
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core.exceptions import ToolError
from core.logger import get_logger

logger = get_logger(__name__)

MAX_COPIES = 999
# Characters Windows doesn't allow in a file name.
FORBIDDEN_NAME_CHARS = frozenset('<>:"/\\|?*')
# Windows' code for "that's on another drive", where a plain rename can't work.
NOT_SAME_DEVICE = 17


@dataclass(frozen=True)
class FileChange:
    source: Path
    destination: Path


class FileTidier:
    """Thread-safe; the log is one JSON line per change, newest last."""

    def __init__(self, log_path: Path) -> None:
        self._log = log_path
        self._lock = threading.Lock()

    def move(self, source: Path, folder: Path) -> FileChange:
        """Moves source into folder (created if needed), keeping its name when it's free."""
        _require_exists(source)
        folder = folder.resolve()
        if folder == source.parent.resolve():
            raise ToolError(f"{source.name} is already in {folder}.")
        if source.is_dir() and (folder == source.resolve() or source.resolve() in folder.parents):
            raise ToolError(f"A folder can't be moved into itself ({source.name}).")
        folder.mkdir(parents=True, exist_ok=True)
        return self._apply(source, free_path(folder / source.name))

    def rename(self, source: Path, new_name: str) -> FileChange:
        """Renames source in place; without an extension, the old one is kept. A change of
        case only ("report" to "Report") is a real rename on Windows, so it's allowed."""
        _require_exists(source)
        name = clean_name(new_name)
        if not Path(name).suffix and source.is_file():
            name += source.suffix
        if name == source.name:
            raise ToolError(f"{source.name} already has that name.")
        target = source.with_name(name)
        if name.lower() == source.name.lower():
            return self._apply(source, target)
        return self._apply(source, free_path(target))

    def last_change(self) -> FileChange | None:
        """The change undo_last would put back, if any."""
        with self._lock:
            changes = self._read_log()
        return changes[-1] if changes else None

    def undo_last(self) -> FileChange:
        """Puts the most recent change back, if nothing has taken its place since."""
        with self._lock:
            changes = self._read_log()
            if not changes:
                raise ToolError("There's no file change to undo.")
            last = changes[-1]
            if not last.destination.exists():
                raise ToolError(f"Can't undo: {last.destination} isn't there any more.")
            if last.source.exists() and not _same_except_case(last.source, last.destination):
                raise ToolError(f"Can't undo: something new is already at {last.source}.")
            last.source.parent.mkdir(parents=True, exist_ok=True)
            _move(last.destination, last.source)
            self._rewrite_log(changes[:-1])
        return FileChange(last.destination, last.source)

    def _apply(self, source: Path, destination: Path) -> FileChange:
        """Moves, then logs; if the log can't be written, the move is put back."""
        with self._lock:
            _move(source, destination)
            try:
                self._append(FileChange(source, destination))
            except OSError as e:
                _move(destination, source)
                raise ToolError("Nothing was moved: the undo log couldn't be saved.") from e
        logger.info("Moved a file for the user", extra={"from": str(source), "to": str(destination)})
        return FileChange(source, destination)

    def _read_log(self) -> list[FileChange]:
        """Every logged change; a damaged line (a crash mid-write, say) is skipped."""
        try:
            lines = self._log.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        except OSError as e:
            raise ToolError(f"Couldn't read the undo log: {e}") from e
        changes = []
        for line in lines:
            try:
                entry = json.loads(line)
                changes.append(FileChange(Path(entry["from"]), Path(entry["to"])))
            except (ValueError, KeyError, TypeError):
                continue
        return changes

    def _append(self, change: FileChange) -> None:
        self._log.parent.mkdir(parents=True, exist_ok=True)
        with self._log.open("a", encoding="utf-8") as log:
            log.write(_entry(change) + "\n")

    def _rewrite_log(self, changes: list[FileChange]) -> None:
        """Replaces the log in one step, so a crash leaves the old or the new one, never half."""
        temporary = self._log.with_suffix(".tmp")
        temporary.write_text("".join(_entry(change) + "\n" for change in changes), encoding="utf-8")
        os.replace(temporary, self._log)


def clean_name(name: str) -> str:
    """A file name Windows accepts: forbidden characters and trailing dots or spaces removed."""
    cleaned = "".join(char for char in name if char not in FORBIDDEN_NAME_CHARS and ord(char) >= 32)
    cleaned = cleaned.strip().rstrip(".")
    if not cleaned:
        raise ToolError("The new name is empty once characters Windows doesn't allow are removed.")
    return cleaned


def free_path(target: Path) -> Path:
    """target, or "name (2).ext", "name (3).ext"... when it's taken."""
    if not target.exists():
        return target
    for copy in range(2, MAX_COPIES + 1):
        candidate = target.with_name(f"{target.stem} ({copy}){target.suffix}")
        if not candidate.exists():
            return candidate
    raise ToolError(f"Too many files named like {target.name}.")


def _entry(change: FileChange) -> str:
    return json.dumps({"from": str(change.source), "to": str(change.destination), "at": datetime.now().isoformat()})


def _same_except_case(first: Path, second: Path) -> bool:
    return str(first).lower() == str(second).lower()


def _require_exists(path: Path) -> None:
    if not path.exists():
        raise ToolError(f"{path} doesn't exist. Use find_files_by_name to get the exact path.")


def _move(source: Path, destination: Path) -> None:
    """A rename, which Windows refuses over an existing file; only a move to another drive
    falls back to copying (after checking the name is still free)."""
    try:
        os.rename(source, destination)
    except FileExistsError as e:
        raise ToolError(f"Something appeared at {destination} just now, so nothing was moved.") from e
    except PermissionError as e:
        raise ToolError(f"{source.name} is in use (open in another program?), so it can't be moved.") from e
    except OSError as e:
        if getattr(e, "winerror", None) != NOT_SAME_DEVICE and e.errno != errno.EXDEV:
            raise ToolError(f"Couldn't move {source.name}: {e}") from e
        _move_across_drives(source, destination)


def _move_across_drives(source: Path, destination: Path) -> None:
    if destination.exists():
        raise ToolError(f"Something appeared at {destination} just now, so nothing was moved.")
    try:
        shutil.move(str(source), str(destination))
    except OSError as e:
        raise ToolError(f"Couldn't move {source.name}: {e}") from e
