from __future__ import annotations

from collections.abc import Iterator

import pytest
from PyQt6.QtCore import QAbstractAnimation
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QLabel, QPushButton

from ui.chat.empty_state import HERO_SIZE, SUGGESTIONS, CloudHero, EmptyState


@pytest.fixture
def empty() -> EmptyState:
    return EmptyState()


@pytest.fixture
def hero() -> Iterator[CloudHero]:
    widget = CloudHero()
    yield widget
    widget.hide()


def _cards(empty: EmptyState) -> list[QPushButton]:
    return [b for b in empty.findChildren(QPushButton) if b.objectName() == "SuggestionCard"]


def test_empty_state_shows_six_suggestion_cards(empty: EmptyState) -> None:
    assert [card.text() for card in _cards(empty)] == [text for _, text in SUGGESTIONS]


def test_empty_state_shows_the_headline_in_the_display_face(empty: EmptyState) -> None:
    headline = empty.findChild(QLabel, "EmptyTitle")

    assert (headline.text(), headline.property("display")) == ("WHERE TO?", "true")


@pytest.mark.parametrize("index", range(len(SUGGESTIONS)))
def test_suggestion_card_emits_its_text(empty: EmptyState, index: int) -> None:
    clicked: list[str] = []
    empty.suggestion_clicked.connect(clicked.append)

    _cards(empty)[index].click()

    assert clicked == [SUGGESTIONS[index][1]]


def test_cloud_hero_cruises_while_shown(hero: CloudHero) -> None:
    hero.show()

    assert hero._cruise.state() == QAbstractAnimation.State.Running


def test_cloud_hero_stops_cruising_when_hidden(hero: CloudHero) -> None:
    hero.show()

    hero.hide()

    assert hero._cruise.state() == QAbstractAnimation.State.Stopped


def test_cloud_hero_advance_moves_the_phase(hero: CloudHero) -> None:

    hero._advance(0.25)

    assert hero._phase == 0.25


def test_cloud_hero_paints_the_cloud(hero: CloudHero) -> None:
    hero._advance(0.4)

    image = hero.grab().toImage()

    assert image.size() == HERO_SIZE
    assert image.pixelColor(HERO_SIZE.width() // 2, HERO_SIZE.height() // 2).alpha() > 0


def test_cloud_hero_paint_changes_with_the_phase(hero: CloudHero) -> None:
    hero._advance(0.0)
    first: QImage = hero.grab().toImage()

    hero._advance(0.25)

    assert hero.grab().toImage() != first
