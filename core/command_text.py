"""
Reads a PowerShell command line the way PowerShell will, for core/command_policy.py: which text
is inside quotes (left to right, so a ' inside double quotes doesn't fool it), what a word's
program name is, and whether a program is really Windows' own (a path directly in System32, or
a bare name that PowerShell would find there first). Text and file-system lookups only.
"""

from __future__ import annotations

import os
from pathlib import Path

# PowerShell also treats curly quotes as quotes; nothing needs them, so they're refused.
CURLY_QUOTES = frozenset("\u2018\u2019\u201a\u201b\u201c\u201d\u201e")
EXECUTABLE_EXTENSIONS = (".exe", ".com", ".bat", ".cmd")
# Where winget really lives: an app alias in the user's WindowsApps folder.
WINDOWS_APPS = Path("~/AppData/Local/Microsoft/WindowsApps")
APP_ALIAS_TOOLS = frozenset({"winget"})


def blank_single_quoted(command: str) -> str | None:
    """command with the inside of single-quoted text removed ('' stays) and any ' inside
    double-quoted text replaced, so the rest can be checked for code. Single-quoted text is
    literal in PowerShell; double-quoted text still expands $(...), so it stays visible. None
    when a quote is left open or curly quotes are used."""
    if any(char in CURLY_QUOTES for char in command):
        return None
    out: list[str] = []
    inside: str | None = None
    for char in command:
        if inside is None:
            inside = char if char in "'\"" else None
            out.append(char)
        elif char == inside:
            inside = None
            out.append(char)
        elif inside == '"':
            out.append("_" if char == "'" else char)
    return None if inside else "".join(out)


def program_name(word: str) -> str:
    """The command's bare name: no quotes, no path, no ".exe"."""
    bare = word.strip("'\"").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return bare.removesuffix(".exe")


def has_path(word: str) -> bool:
    bare = word.strip("'\"")
    return "\\" in bare or "/" in bare or ":" in bare


def is_system_path(word: str) -> bool:
    """A path to a program directly inside System32 or SysWOW64, where only administrators can
    write. Any other path, even one in the Windows folder (whose Temp folder anyone can write
    to), could be any file named like an allowed tool."""
    try:
        folder = Path(word.strip("'\"")).resolve().parent
    except (OSError, ValueError):
        return False
    return folder in system_folders()


def resolves_to_windows(name: str) -> bool:
    """True when a bare program name is found first in Windows' own folders on the PATH that
    PowerShell will search (it never looks in the current folder). Another folder earlier on
    the PATH, Git's tools say, could hold a different "hostname"."""
    allowed = system_folders()
    if name in APP_ALIAS_TOOLS:
        allowed = allowed | {Path(os.path.abspath(WINDOWS_APPS.expanduser()))}
    found = first_on_path(name)
    return found is not None and found.parent in allowed


def first_on_path(name: str) -> Path | None:
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        if not folder.strip():
            continue
        for extension in EXECUTABLE_EXTENSIONS:
            candidate = Path(os.path.abspath(Path(folder.strip().strip('"')) / f"{name}{extension}"))
            # Not resolved: winget's app alias is a link that doesn't resolve to a plain file.
            if candidate.exists():
                return candidate
    return None


def system_folders() -> set[Path]:
    windows = Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
    return {Path(os.path.abspath(windows / name)) for name in ("System32", "SysWOW64")}
