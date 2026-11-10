from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from ui.chat.thinking_indicator import (
    PHRASES,
    SHOW_ELAPSED_AFTER_SECONDS,
    TICKS_PER_PHRASE,
    ThinkingIndicator,
    _shimmer,
)
from ui.theme.tokens import CLOUD_GOLD, CLOUD_GOLD_DEEP, TEXT


@pytest.fixture
def indicator(qapp: object) -> ThinkingIndicator:
    return ThinkingIndicator()


def test_init_starts_hidden_and_still(indicator: ThinkingIndicator) -> None:
    assert (indicator.isHidden(), indicator.is_animating()) == (True, False)


def test_start_shows_the_first_phrase_and_animates(indicator: ThinkingIndicator) -> None:
    indicator.start()

    assert (indicator.isHidden(), indicator.is_animating(), indicator.phrase()) == (False, True, PHRASES[0])


def test_stop_hides_and_freezes(indicator: ThinkingIndicator) -> None:
    indicator.start()

    indicator.stop()

    assert (indicator.isHidden(), indicator.is_animating()) == (True, False)


def test_advance_changes_the_text_every_tick(indicator: ThinkingIndicator) -> None:
    indicator.start()
    before = indicator.text()

    indicator._advance()

    assert indicator.text() != before


def test_advance_moves_on_to_the_next_phrase(indicator: ThinkingIndicator) -> None:
    indicator.start()

    for _ in range(TICKS_PER_PHRASE):
        indicator._advance()

    assert indicator.phrase() == PHRASES[1]


def test_render_adds_a_seconds_counter_on_a_long_wait(indicator: ThinkingIndicator, mocker: MockerFixture) -> None:
    clock = mocker.patch("ui.chat.thinking_indicator.time.monotonic", return_value=100.0)
    indicator.start()
    clock.return_value = 100.0 + SHOW_ELAPSED_AFTER_SECONDS + 7

    indicator._advance()

    assert f"{SHOW_ELAPSED_AFTER_SECONDS + 7}s" in indicator.text()


def test_render_has_no_counter_on_a_short_wait(indicator: ThinkingIndicator, mocker: MockerFixture) -> None:
    mocker.patch("ui.chat.thinking_indicator.time.monotonic", return_value=100.0)
    indicator.start()

    assert CLOUD_GOLD_DEEP not in indicator.text()


def test_shimmer_highlights_the_characters_under_the_band() -> None:
    html = _shimmer("abc", 0)

    assert (html.count(TEXT), html.count(CLOUD_GOLD)) == (1, 2)


def test_shimmer_escapes_markup() -> None:
    assert "&lt;" in _shimmer("<b>", 5)
