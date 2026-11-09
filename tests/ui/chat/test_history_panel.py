from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton
from pytest_mock import MockerFixture

from core.exceptions import NimbusError
from models.chat import ConversationSummary
from ui.api_client import ApiClient
from ui.chat.history_panel import HistoryPanel


def _synchronous(fn: Any, ok: Any, err: Any = None) -> None:
    try:
        result = fn()
    except NimbusError as e:
        if err is not None:
            err(str(e))
        return
    ok(result)


@pytest.fixture
def api(mocker: MockerFixture) -> Mock:
    fake = mocker.Mock(spec=ApiClient)
    fake.conversations.return_value = [
        ConversationSummary(id="c2", title="Battery check", updated_at=datetime(2026, 11, 10, 9, 5)),
        ConversationSummary(id="c1", title="Find my resume", updated_at=datetime(2026, 11, 9, 18, 30)),
    ]
    return fake


@pytest.fixture
def panel(mocker: MockerFixture, api: Mock) -> HistoryPanel:
    mocker.patch("ui.chat.history_panel.run_in_background", side_effect=_synchronous)
    return HistoryPanel(api)


def _button(panel: HistoryPanel, text: str) -> QPushButton:
    return next(b for b in panel.findChildren(QPushButton) if b.text() == text)


def test_refresh_lists_conversations_newest_first(panel: HistoryPanel) -> None:
    panel.refresh()

    first = panel._list.item(0)
    assert first.text() == "Battery check\n10 Nov 2026, 09:05"
    assert first.data(Qt.ItemDataRole.UserRole) == "c2"
    assert panel._message.text() == ""


def test_refresh_replaces_the_previous_list(panel: HistoryPanel) -> None:
    panel.refresh()

    panel.refresh()

    assert panel._list.count() == 2


def test_refresh_says_when_there_are_no_chats(panel: HistoryPanel, api: Mock) -> None:
    api.conversations.return_value = []

    panel.refresh()

    assert panel._message.text() == "No chats yet."


def test_refresh_shows_a_load_error(panel: HistoryPanel, api: Mock) -> None:
    api.conversations.side_effect = NimbusError("Couldn't reach Nimbus's engine.")

    panel.refresh()

    assert panel._message.text() == "Couldn't reach Nimbus's engine."


def test_clicking_a_conversation_emits_opened(panel: HistoryPanel) -> None:
    panel.refresh()
    opened: list[str] = []
    panel.opened.connect(opened.append)

    panel._list.itemClicked.emit(panel._list.item(1))

    assert opened == ["c1"]


def test_back_button_emits_back(panel: HistoryPanel) -> None:
    received: list[None] = []
    panel.back.connect(lambda: received.append(None))

    _button(panel, "← Back to chat").click()

    assert received == [None]


def test_delete_selected_deletes_and_reloads(panel: HistoryPanel, api: Mock) -> None:
    panel.refresh()
    panel._list.setCurrentRow(1)

    _button(panel, "Delete selected").click()

    api.delete_conversation.assert_called_once_with("c1")
    assert api.conversations.call_count == 2


def test_delete_selected_does_nothing_without_a_selection(panel: HistoryPanel, api: Mock) -> None:
    panel.refresh()

    _button(panel, "Delete selected").click()

    api.delete_conversation.assert_not_called()


def test_delete_selected_shows_a_delete_error(panel: HistoryPanel, api: Mock) -> None:
    panel.refresh()
    panel._list.setCurrentRow(0)
    api.delete_conversation.side_effect = NimbusError("Chat not found")

    _button(panel, "Delete selected").click()

    assert panel._message.text() == "Chat not found"
