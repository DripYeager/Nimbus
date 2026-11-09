from __future__ import annotations

from models.schema import IndexStatus
from ui.status_text import describe_status


def test_describe_status_reports_paused_first() -> None:
    status = IndexStatus(is_paused=True, pending_files=5, is_scanning=True)

    assert describe_status(status) == "Indexing paused"


def test_describe_status_counts_indexed_and_failed_files_as_done() -> None:
    status = IndexStatus(content_files=2500, indexed_files=1200, failed_files=34, pending_files=1266)

    assert describe_status(status) == "Learning your files · 1,234 of 2,500"


def test_describe_status_reports_scanning_when_nothing_is_pending() -> None:
    assert describe_status(IndexStatus(is_scanning=True)) == "Looking for new files…"


def test_describe_status_reports_ready_with_known_file_count() -> None:
    assert describe_status(IndexStatus(cataloged_files=12345)) == "Ready · 12,345 files known"
