from __future__ import annotations

import pytest

from ui.chat.conversation_column import ConversationColumn


@pytest.fixture
def column(qapp: object) -> ConversationColumn:
    return ConversationColumn()


def test_has_messages_is_false_for_a_new_column(column: ConversationColumn) -> None:
    assert not column.has_messages()


def test_add_user_message_reports_new_content(column: ConversationColumn) -> None:
    added: list[None] = []
    column.content_added.connect(lambda: added.append(None))

    column.add_user_message("hi")

    assert (column.has_messages(), added) == (True, [None])


def test_has_open_card_is_true_until_the_card_is_answered(column: ConversationColumn) -> None:
    card = column.add_confirmation("Open Notepad")
    before = column.has_open_card()

    card._decide(True, False)

    assert (before, column.has_open_card()) == (True, False)


def test_clear_forgets_open_cards(column: ConversationColumn) -> None:
    column.add_confirmation("Open Notepad")

    column.clear()

    assert column.has_open_card() is False
