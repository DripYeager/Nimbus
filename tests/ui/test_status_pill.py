from __future__ import annotations

from ui.settings.status_pill import StatusPill


def test_status_pill_show_status_sets_text_and_state() -> None:
    pill = StatusPill()
    pill.show_status("Connected", "ok")
    assert (pill.text(), pill.state(), pill.isHidden()) == ("Connected", "ok", False)


def test_status_pill_clear_hides_it() -> None:
    pill = StatusPill()
    pill.show_status("Testing…", "busy")
    pill.clear()
    assert pill.isHidden()
