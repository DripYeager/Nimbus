"""
Walks a source folder and yields every file worth cataloging, pruning excluded folders
before descending into them. Only stats files — never opens or reads them, and doesn't
decide what to do with what it finds.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from core.index_rules import IndexRules
from core.logger import get_logger
from models.schema import ScannedFile

logger = get_logger(__name__)


def scan_source(root: Path, rules: IndexRules) -> Iterator[ScannedFile]:
    """Yields every non-excluded file under root. Uses os.scandir rather than rglob so an
    excluded folder like node_modules is skipped without ever being listed."""
    pending = [root]
    while pending:
        directory = pending.pop()
        for entry in _list_directory(directory):
            path = Path(entry.path)
            if entry.is_dir(follow_symlinks=False):
                # A junction reports as a real folder but can point anywhere, even outside every source.
                if not _is_junction(entry) and not rules.is_excluded_dir(path):
                    pending.append(path)
            elif entry.is_file(follow_symlinks=False) and not rules.is_excluded_file(path):
                scanned = _stat_entry(entry)
                if scanned is not None:
                    yield scanned


def _list_directory(directory: Path) -> list[os.DirEntry[str]]:
    """Lists one folder, treating an unreadable one as empty — a locked folder on a work
    laptop is normal, not an error worth stopping the scan for."""
    try:
        with os.scandir(directory) as entries:
            return list(entries)
    except OSError as e:
        logger.info("Skipping unreadable folder", extra={"path": str(directory), "error": str(e)})
        return []


def _is_junction(entry: os.DirEntry[str]) -> bool:
    """True for a Windows directory junction (DirEntry.is_junction is Python 3.12+)."""
    is_junction = getattr(entry, "is_junction", None)
    return bool(is_junction and is_junction())


def _stat_entry(entry: os.DirEntry[str]) -> ScannedFile | None:
    """Reads size and mtime for one entry, or None if it vanished mid-scan."""
    try:
        stat = entry.stat(follow_symlinks=False)
    except OSError:
        return None
    return ScannedFile(path=Path(entry.path), size_bytes=stat.st_size, modified_ts=stat.st_mtime)
