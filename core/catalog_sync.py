"""
Compares what's on disk with what the catalog remembers and decides what changed: new or
modified files to (re)index, files that became name-only, and files that disappeared. Pure
decision-making over scan results, does not touch disk, the catalog, or the vector store.
"""

from __future__ import annotations

from collections.abc import Iterable

from core.file_catalog import folder_prefix, path_key
from core.index_rules import IndexRules
from models.schema import CatalogEntry, CatalogStatus, ScannedFile, SyncPlan

# A finished file stays finished until it changes on disk; a failed one isn't retried on every
# launch either, only when it changes, or on an explicit rebuild.
SETTLED_STATUSES = frozenset({CatalogStatus.INDEXED, CatalogStatus.FAILED})


def plan_sync(
    scanned: Iterable[ScannedFile], snapshot: dict[str, CatalogEntry], rules: IndexRules, seen: set[str]
) -> SyncPlan:
    """Decides the catalog/queue changes for one batch of scanned files. Adds each file's key
    to seen, so the caller can find vanished files once every source has been scanned."""
    plan = SyncPlan()
    for file in scanned:
        key = path_key(file.path)
        seen.add(key)
        _plan_one(file, snapshot.get(key), rules, plan)
    return plan


def find_vanished(snapshot: dict[str, CatalogEntry], seen: set[str], rules: IndexRules) -> list[CatalogEntry]:
    """Cataloged files that weren't seen in this scan. Files under a source folder that's
    currently missing (an unplugged drive) are kept rather than wiped."""
    missing_roots = [folder_prefix(s.path) for s in rules.sources if not s.path.is_dir()]
    return [
        entry
        for key, entry in snapshot.items()
        if key not in seen and not any(key.startswith(root) for root in missing_roots)
    ]


def target_status(file: ScannedFile, rules: IndexRules) -> CatalogStatus:
    """PENDING for a file whose contents should be read, NAME_ONLY otherwise."""
    if rules.should_read_contents(file.path, file.size_bytes):
        return CatalogStatus.PENDING
    return CatalogStatus.NAME_ONLY


def _plan_one(file: ScannedFile, existing: CatalogEntry | None, rules: IndexRules, plan: SyncPlan) -> None:
    """Adds whatever one file needs to plan."""
    wanted = target_status(file, rules)
    unchanged = existing is not None and _is_unchanged(file, existing)
    if wanted is CatalogStatus.NAME_ONLY:
        # A pending or failed file can still hold rows from an earlier successful index, and a
        # pending one may already be sitting in the queue.
        if existing is not None and existing.status is not CatalogStatus.NAME_ONLY:
            plan.drop_content.append(file.path)
        if not unchanged or existing.status is not CatalogStatus.NAME_ONLY:
            plan.upserts.append(_entry(file, CatalogStatus.NAME_ONLY))
        return
    if unchanged and existing.status in SETTLED_STATUSES:
        return
    if not unchanged or existing.status is not CatalogStatus.PENDING:
        plan.upserts.append(_entry(file, CatalogStatus.PENDING))
    plan.to_queue.append((file.path, file.modified_ts))


def _is_unchanged(file: ScannedFile, existing: CatalogEntry) -> bool:
    """Same size and mtime, the same signal every backup and sync tool trusts."""
    return existing.size_bytes == file.size_bytes and existing.modified_ts == file.modified_ts


def _entry(file: ScannedFile, status: CatalogStatus) -> CatalogEntry:
    return CatalogEntry(path=file.path, size_bytes=file.size_bytes, modified_ts=file.modified_ts, status=status)
