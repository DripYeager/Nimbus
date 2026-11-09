from __future__ import annotations

import threading
from pathlib import Path

from core.index_queue import IndexQueue

DOCS = Path("C:/Docs")
NO_WAIT = 0.01


def _drain(queue: IndexQueue) -> list[Path]:
    popped = []
    while (path := queue.pop(timeout=NO_WAIT)) is not None:
        popped.append(path)
    return popped


def test_pop_returns_none_when_nothing_arrives() -> None:
    assert IndexQueue().pop(timeout=NO_WAIT) is None


def test_pop_returns_the_newest_file_first() -> None:
    queue = IndexQueue()
    queue.push(DOCS / "2019.txt", modified_ts=100.0)
    queue.push(DOCS / "2026.txt", modified_ts=300.0)
    queue.push(DOCS / "2022.txt", modified_ts=200.0)

    assert _drain(queue) == [DOCS / "2026.txt", DOCS / "2022.txt", DOCS / "2019.txt"]


def test_pop_returns_an_urgent_file_before_any_newer_one() -> None:
    queue = IndexQueue()
    queue.push(DOCS / "new.txt", modified_ts=999.0)
    queue.push(DOCS / "just-saved.txt", modified_ts=1.0, urgent=True)

    assert queue.pop(timeout=NO_WAIT) == DOCS / "just-saved.txt"


def test_push_de_duplicates_the_same_path_ignoring_case() -> None:
    queue = IndexQueue()
    queue.push(DOCS / "a.txt", modified_ts=1.0)
    queue.push(Path("c:/docs/A.TXT"), modified_ts=1.0)

    assert len(_drain(queue)) == 1


def test_push_again_as_urgent_bumps_a_waiting_path_to_the_front() -> None:
    queue = IndexQueue()
    queue.push(DOCS / "newest.txt", modified_ts=999.0)
    queue.push(DOCS / "old.txt", modified_ts=1.0)
    queue.push(DOCS / "old.txt", modified_ts=1.0, urgent=True)

    assert _drain(queue) == [DOCS / "old.txt", DOCS / "newest.txt"]


def test_len_counts_distinct_waiting_paths() -> None:
    queue = IndexQueue()
    queue.push(DOCS / "a.txt", modified_ts=1.0)
    queue.push(DOCS / "a.txt", modified_ts=2.0)
    queue.push(DOCS / "b.txt", modified_ts=1.0)

    assert len(queue) == 2


def test_discard_drops_a_waiting_path() -> None:
    queue = IndexQueue()
    queue.push(DOCS / "a.txt", modified_ts=1.0)

    queue.discard(DOCS / "A.txt")

    assert queue.pop(timeout=NO_WAIT) is None


def test_discard_ignores_a_path_that_is_not_waiting() -> None:
    queue = IndexQueue()

    queue.discard(DOCS / "a.txt")

    assert len(queue) == 0


def test_discard_under_drops_a_folder_but_not_its_same_prefix_sibling() -> None:
    queue = IndexQueue()
    queue.push(DOCS / "a.txt", modified_ts=1.0)
    queue.push(DOCS / "sub" / "b.txt", modified_ts=1.0)
    queue.push(Path("C:/Docs2/keep.txt"), modified_ts=1.0)

    queue.discard_under(DOCS)

    assert _drain(queue) == [Path("C:/Docs2/keep.txt")]


def test_clear_empties_the_queue() -> None:
    queue = IndexQueue()
    queue.push(DOCS / "a.txt", modified_ts=1.0)

    queue.clear()

    assert queue.pop(timeout=NO_WAIT) is None


def test_pop_wakes_up_as_soon_as_another_thread_pushes() -> None:
    queue = IndexQueue()
    popped: list[Path | None] = []
    waiter = threading.Thread(target=lambda: popped.append(queue.pop(timeout=5.0)))
    waiter.start()

    queue.push(DOCS / "a.txt", modified_ts=1.0)
    waiter.join(timeout=5.0)

    assert popped == [DOCS / "a.txt"]
