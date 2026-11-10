from __future__ import annotations

import pytest

from ui.theme.settings_styles import SETTINGS_QSS
from ui.theme.tokens import CLOUD_GOLD, GI_ORANGE


def test_settings_qss_balances_its_braces() -> None:
    assert SETTINGS_QSS.count("{") == SETTINGS_QSS.count("}")


def test_settings_qss_uses_the_theme_tokens() -> None:
    assert GI_ORANGE in SETTINGS_QSS and CLOUD_GOLD in SETTINGS_QSS


@pytest.mark.parametrize(
    "selector",
    [
        "QPushButton#NavItem:checked",
        "QFrame#SettingsBar",
        'QLabel#BarStatus[state="success"]',
        "QFrame#Card",
        "QFrame#FolderRow",
        "QPushButton#AddFolderButton",
        "QPushButton#TypeChip:checked",
        "QPushButton#ProviderCard:checked",
        'QLabel#Badge[tone="local"]',
        'QFrame#StatusPill[state="error"]',
        "QKeySequenceEdit#Keycap QLineEdit",
        "QWidget#OnboardingWindow",
        "QFrame#WizardFooter",
    ],
)
def test_settings_qss_styles_selector(selector: str) -> None:
    assert selector in SETTINGS_QSS
