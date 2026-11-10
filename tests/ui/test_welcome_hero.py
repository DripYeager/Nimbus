from __future__ import annotations

from ui.onboarding.welcome_hero import HERO_HEIGHT, WelcomeHero


def test_welcome_hero_paints_at_fixed_height() -> None:
    hero = WelcomeHero()
    hero.resize(600, HERO_HEIGHT)
    assert hero.grab().height() == HERO_HEIGHT
