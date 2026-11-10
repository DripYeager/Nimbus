"""
Saves and finds the user's quick notes, stored as plain markdown files in the Nimbus notes
folder. Does not touch any other folder and does not index notes for semantic search.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from config.paths import notes_dir
from core.exceptions import ToolError
from core.logger import get_logger
from models.system import NOTE_PREVIEW_CHARS, NoteMatch

logger = get_logger(__name__)

NOTE_SUFFIX = ".md"
FILENAME_TIMESTAMP_FORMAT = "%Y-%m-%d_%H%M%S"
SLUG_MAX_CHARS = 40
DEFAULT_SLUG = "note"
DERIVED_TITLE_MAX_CHARS = 60
TITLE_PREFIX = "# "
DEFAULT_SEARCH_LIMIT = 5
DEFAULT_LIST_LIMIT = 10
NON_SLUG_CHARS = re.compile(r"[^a-z0-9]+")
WHITESPACE = re.compile(r"\s+")


def save_note(title: str, body: str) -> Path:
    """
    Writes a new markdown note into the notes folder, creating the folder if needed.

    A note with only a body gets its title from the body's first line, so every note has a
    heading to show in search results.

    Returns:
        The path of the new note file.

    Raises:
        ToolError: If both title and body are empty, or the file couldn't be written.
    """
    title, body = title.strip(), body.strip()
    if not title and not body:
        raise ToolError("Can't save an empty note. Give it a title or some text.")
    title = title or _derive_title(body)
    path = _unique_note_path(notes_dir(), title)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{TITLE_PREFIX}{title}\n\n{body}\n", encoding="utf-8")
    except OSError as e:
        raise ToolError(f"Couldn't save the note to {path}: {e}. Check the notes folder is writable.") from e
    logger.info("Saved note", extra={"path": str(path)})
    return path


def search_notes(query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[NoteMatch]:
    """
    Finds notes whose title or body contains every word of query, ignoring case.

    Args:
        query: Words to look for. Blank returns the most recent notes instead.
        limit: Maximum number of notes to return.

    Returns:
        Matching notes, newest first.

    Raises:
        ToolError: If limit is less than 1.
    """
    _require_positive_limit(limit)
    words = query.lower().split()
    if not words:
        return list_notes(limit)
    matches = [match for match, text in _load_notes() if all(word in text for word in words)]
    return matches[:limit]


def list_notes(limit: int = DEFAULT_LIST_LIMIT) -> list[NoteMatch]:
    """
    Lists the most recently modified notes, newest first.

    Raises:
        ToolError: If limit is less than 1.
    """
    _require_positive_limit(limit)
    return [match for match, _ in _load_notes()[:limit]]


def _require_positive_limit(limit: int) -> None:
    """Rejects limits that could never return anything."""
    if limit < 1:
        raise ToolError(f"limit must be at least 1, got {limit}.")


def _derive_title(body: str) -> str:
    """The body's first line, trimmed to a heading-sized length."""
    first_line = body.splitlines()[0].strip()
    return first_line[:DERIVED_TITLE_MAX_CHARS].rstrip()


def _slugify(title: str) -> str:
    """A filename-safe, lowercase, hyphenated version of title."""
    slug = NON_SLUG_CHARS.sub("-", title.lower()).strip("-")
    return slug[:SLUG_MAX_CHARS].rstrip("-") or DEFAULT_SLUG


def _unique_note_path(folder: Path, title: str) -> Path:
    """A new timestamped path in folder that doesn't clash with a note saved in the same second."""
    stem = f"{datetime.now().strftime(FILENAME_TIMESTAMP_FORMAT)}_{_slugify(title)}"
    path = folder / f"{stem}{NOTE_SUFFIX}"
    counter = 2
    while path.exists():
        path = folder / f"{stem}-{counter}{NOTE_SUFFIX}"
        counter += 1
    return path


def _load_notes() -> list[tuple[NoteMatch, str]]:
    """Every readable note, newest first, paired with its lowercased full text for matching."""
    folder = notes_dir()
    if not folder.is_dir():
        return []
    paths = sorted(folder.glob(f"*{NOTE_SUFFIX}"), key=_modified_sort_key, reverse=True)
    notes = [_read_note(path) for path in paths]
    return [note for note in notes if note is not None]


def _modified_sort_key(path: Path) -> tuple[float, str]:
    """Sorts by modification time, falling back to the timestamped filename for ties."""
    try:
        return path.stat().st_mtime, path.name
    except OSError:
        return 0.0, path.name


def _read_note(path: Path) -> tuple[NoteMatch, str] | None:
    """Parses one note file, or None (logged) if it can't be read."""
    try:
        text = path.read_text(encoding="utf-8")
        modified_at = datetime.fromtimestamp(path.stat().st_mtime)
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("Skipped unreadable note", extra={"path": str(path), "error": str(e)})
        return None
    title, body = _split_title(text, fallback=path.stem)
    preview = WHITESPACE.sub(" ", body).strip()[:NOTE_PREVIEW_CHARS]
    match = NoteMatch(path=str(path), title=title, modified_at=modified_at, preview=preview)
    return match, f"{title}\n{body}".lower()


def _split_title(text: str, fallback: str) -> tuple[str, str]:
    """Splits a note into its "# " heading and the rest; notes without one use fallback as title."""
    first_line, _, rest = text.partition("\n")
    if first_line.startswith(TITLE_PREFIX):
        return first_line[len(TITLE_PREFIX) :].strip(), rest.strip()
    return fallback, text.strip()
