"""
A de-duplicating priority queue of files waiting for content indexing. Files the user just
touched (watcher events) jump the line; otherwise the most recently modified files go first,
so this week's documents are searchable long before a ten-year-old archive is. Owns ordering
only; does not index anything.
"""

from __future__ import annotations

import heapq
import itertools
import threading
from pathlib import Path

from core.file_catalog import folder_prefix, path_key

# Watcher events sort ahead of every mtime-based priority (which are negative timestamps).
URGENT_PRIORITY = float("-inf")


class IndexQueue:
    """Thread-safe: the scanner and the watcher push, the single index worker pops."""

    def __init__(self) -> None:
        self._heap: list[tuple[float, int, str]] = []
        self._paths: dict[str, Path] = {}
        self._counter = itertools.count()
        self._condition = threading.Condition()

    def push(self, path: Path, modified_ts: float, urgent: bool = False) -> None:
        """Queues path, or bumps its priority if it's already waiting."""
        priority = URGENT_PRIORITY if urgent else -modified_ts
        key = path_key(path)
        with self._condition:
            self._paths[key] = path
            heapq.heappush(self._heap, (priority, next(self._counter), key))
            self._condition.notify()

    def pop(self, timeout: float) -> Path | None:
        """Returns the highest-priority waiting path, or None if nothing arrives within timeout."""
        with self._condition:
            if not self._paths:
                self._condition.wait(timeout)
            while self._heap:
                _, _, key = heapq.heappop(self._heap)
                # A re-pushed path leaves an older heap entry behind; only the first one popped counts.
                path = self._paths.pop(key, None)
                if path is not None:
                    return path
            return None

    def discard(self, path: Path) -> None:
        """Drops path if it's waiting, e.g. it was deleted before the worker reached it."""
        with self._condition:
            self._paths.pop(path_key(path), None)

    def discard_under(self, root: Path) -> None:
        """Drops every waiting path below root, for a removed source folder."""
        prefix = folder_prefix(root)
        with self._condition:
            for key in [k for k in self._paths if k.startswith(prefix)]:
                del self._paths[key]

    def clear(self) -> None:
        with self._condition:
            self._paths.clear()
            self._heap.clear()

    def __len__(self) -> int:
        with self._condition:
            return len(self._paths)
