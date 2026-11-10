from __future__ import annotations

from ui.onboarding.step_progress import StepProgress


def test_step_progress_set_step_clamps_to_range() -> None:
    progress = StepProgress(["One", "Two", "Three"])
    progress.set_step(9)
    assert progress.current_step() == 2


def test_step_progress_paints_without_error() -> None:
    progress = StepProgress(["One", "Two", "Three"])
    progress.resize(400, progress.height())
    progress.set_step(1)
    assert not progress.grab().isNull()
