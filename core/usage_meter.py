"""
Counts model calls per calendar day, persisted to a small JSON file so the count survives a
restart. Owns counting only, enforcing a cap is the caller's decision.
"""

from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path

from core.logger import get_logger

logger = get_logger(__name__)


class UsageMeter:
    """Today's call count, reset automatically when the date changes."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def record_call(self) -> None:
        """Adds one call to today's count."""
        with self._lock:
            today, count = self._read()
            self._write(today, count + 1)

    def calls_today(self) -> int:
        with self._lock:
            return self._read()[1]

    def _read(self) -> tuple[str, int]:
        """(today's ISO date, count), a count from an earlier day reads as 0."""
        today = date.today().isoformat()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return today, 0
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Usage file unreadable, starting the count over", extra={"error": str(e)})
            return today, 0
        return today, int(data.get("count", 0)) if data.get("date") == today else 0

    def _write(self, today: str, count: int) -> None:
        """Persists the count; losing one write only under-counts, so failures are logged."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps({"date": today, "count": count}), encoding="utf-8")
        except OSError as e:
            logger.warning("Couldn't save the usage count", extra={"error": str(e)})
