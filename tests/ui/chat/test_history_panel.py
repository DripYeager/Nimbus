from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QLabel, QToolButton
from pytest_mock import MockerFixture

from core.exceptions import NimbusError
from models.chat import ConversationSummary
from ui.api_client import ApiClient
from ui.chat.history_panel import ConversationRow, HistoryPanel


def _synchronous(fn: Any, ok: Any, err: Any = None) -> None:
    """run_in_background without the thread pool, including the error path."""
    try:
        result = fn()
    except NimbusError as e:
        if err is not None:
            err(str(e))
        return
    ok(result)


def _summary(conversation_id: str, title: str) -> ConversationSummary:
    return ConversationSummary(id=conversation_id, title=title, updated_at=datetime(2026, 11, 10, 9, 5))


@pytest.fixture
def api(mocker: MockerFixture) -> Mock:
    fake = mocker.Mock(spec=ApiClient)
    fake.conversations.return_value = [_summary("c2", "Battery check"), _summary("c1", "Find my RESUME")]
    return fake


@pytest.fixture
def panel(mocker: MockerFixture, api: Mock) -> HistoryPanel:
    mocker.patch("ui.chat.history_panel.run_in_background", side_effect=_synchronous)
    return HistoryPanel(api)


@pytest.fixture
def loaded(panel: HistoryPanel) -> HistoryPanel:
    panel.refresh()
    return panel


def _visible_titles(panel: HistoryPanel) -> list[str]:
    return [row.title for row in panel._rows if not row.isHidden()]


def _delete_button(row: ConversationRow) -> QToolButton:
    return row.findChild(QToolButton)


def test_conversation_row_shows_the_title_and_date() -> None:
    row = ConversationRow(_summary("c1", "Battery check"))

    assert [label.text() for label in row.findChildren(QLabel) if label.text()] == [
        "Battery check",
        "10 Nov 2026 · 09:05",
    ]


def test_conversation_row_delete_button_requests_its_own_deletion() -> None:
    row = ConversationRow(_summary("c1", "Battery check"))
    requested: list[str] = []
    row.delete_requested.connect(requested.append)

    _delete_button(row).click()

    assert requested == ["c1"]


def test_refresh_lists_conversations_in_the_order_given(loaded: HistoryPanel) -> None:
    assert [row.conversation_id for row in loaded._rows] == ["c2", "c1"]


def test_refresh_hides_the_message_when_there_are_chats(loaded: HistoryPanel) -> None:
    assert loaded._message.isHidden()


def test_refresh_replaces_the_previous_rows(loaded: HistoryPanel) -> None:
    loaded.refresh()

    assert len(loaded._rows) == 2


def test_refresh_says_when_there_are_no_chats(panel: HistoryPanel, api: Mock) -> None:
    api.conversations.return_value = []

    panel.refresh()

    assert (panel._message.isHidden(), panel._message.text()) == (
        False,
        "No chats yet. Your conversations will show up here.",
    )


def test_refresh_shows_a_load_error(panel: HistoryPanel, api: Mock) -> None:
    api.conversations.side_effect = NimbusError("Couldn't reach Nimbus's engine.")

    panel.refresh()

    assert panel._message.text() == "Couldn't reach Nimbus's engine."


def test_clicking_a_row_emits_opened(loaded: HistoryPanel) -> None:
    opened: list[str] = []
    loaded.opened.connect(opened.append)

    loaded._rows[1].click()

    assert opened == ["c1"]


def test_filter_hides_rows_that_do_not_match(loaded: HistoryPanel) -> None:
    loaded._search.setText("battery")

    assert _visible_titles(loaded) == ["Battery check"]


def test_filter_ignores_case(loaded: HistoryPanel) -> None:
    loaded._search.setText("resume")

    assert _visible_titles(loaded) == ["Find my RESUME"]


def test_filter_ignores_surrounding_whitespace(loaded: HistoryPanel) -> None:
    loaded._search.setText("  Battery  ")

    assert _visible_titles(loaded) == ["Battery check"]


def test_filter_shows_every_row_when_cleared(loaded: HistoryPanel) -> None:
    loaded._search.setText("battery")

    loaded._search.clear()

    assert _visible_titles(loaded) == ["Battery check", "Find my RESUME"]


def test_refresh_keeps_the_current_search_applied(panel: HistoryPanel) -> None:
    panel._search.setText("resume")

    panel.refresh()

    assert _visible_titles(panel) == ["Find my RESUME"]


def test_delete_removes_the_conversation(loaded: HistoryPanel, api: Mock) -> None:
    _delete_button(loaded._rows[1]).click()

    api.delete_conversation.assert_called_once_with("c1")


def test_delete_reloads_the_list(loaded: HistoryPanel, api: Mock) -> None:
    _delete_button(loaded._rows[1]).click()

    assert api.conversations.call_count == 2


def test_delete_does_not_open_the_conversation(loaded: HistoryPanel) -> None:
    opened: list[str] = []
    loaded.opened.connect(opened.append)

    _delete_button(loaded._rows[0]).click()

    assert opened == []


def test_delete_shows_a_delete_error(loaded: HistoryPanel, api: Mock) -> None:
    api.delete_conversation.side_effect = NimbusError("Chat not found")

    _delete_button(loaded._rows[0]).click()

    assert (loaded._message.isHidden(), loaded._message.text()) == (False, "Chat not found")
