from __future__ import annotations

import pytest

from ui.theme.stylesheet import build_stylesheet
from ui.theme.tokens import CLOUD_GOLD, FONT_FAMILY, NIGHT


def test_build_stylesheet_balances_its_braces() -> None:
    stylesheet = build_stylesheet()

    assert stylesheet.count("{") == stylesheet.count("}")


def test_build_stylesheet_leaves_no_unformatted_placeholders() -> None:
    assert "{{" not in build_stylesheet()


def test_build_stylesheet_uses_the_theme_tokens() -> None:
    stylesheet = build_stylesheet()

    assert all(token in stylesheet for token in (CLOUD_GOLD, FONT_FAMILY, NIGHT))


@pytest.mark.parametrize(
    "selector",
    [
        "QFrame#ChatPanel",
        "QLabel#HeaderStatus",
        'QLabel#PrivacyBadge[cloud="true"]',
        'QLabel#ToolChip[status="failed"]',
        "QPushButton#SourceCard",
        "QFrame#ConfirmCard",
        "QPlainTextEdit#ChatInput",
        "QPushButton#SendButton:disabled",
        "QListWidget#HistoryList",
        "QToolButton#HeaderButton",
        'QPushButton[variant="primary"]',
        'QPushButton[variant="chip"]',
        'QLabel[role="muted"]',
        'QLabel[role="error"]',
    ],
)
def test_build_stylesheet_styles_the_widgets_that_opt_in(selector: str) -> None:
    assert selector in build_stylesheet()
