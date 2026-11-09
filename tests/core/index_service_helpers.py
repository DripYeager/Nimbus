"""Shared helpers for the IndexService tests (fixtures live in conftest.py)."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from core.file_catalog import FileCatalog
from core.index_service import IndexService
from models.schema import CatalogStatus

MODEL = "test/fake-model"
ServiceFactory = Callable[[], IndexService]


def write_file(path: Path, text: str = "quarterly numbers look good") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def wait_until(condition: Callable[[], bool], timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


def start_and_index(service: IndexService, expected_indexed: int) -> None:
    service.start(MODEL)
    assert wait_until(lambda: service.status().indexed_files == expected_indexed)


def catalog_statuses(catalog: FileCatalog) -> dict[str, CatalogStatus]:
    return {Path(entry.path).name: entry.status for entry in catalog.snapshot().values()}


def drain_queue(service: IndexService) -> list[Path]:
    queue = service._queue
    popped = []
    while (path := queue.pop(timeout=0.01)) is not None:
        popped.append(path)
    return popped
