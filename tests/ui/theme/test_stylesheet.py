from __future__ import annotations

import pytest

from ui.theme.chat_styles import CHAT_QSS
from ui.theme.settings_styles import SETTINGS_QSS
from ui.theme.stylesheet import build_stylesheet
from ui.theme.tokens import CLOUD_GOLD, DISPLAY_FONT_FAMILY, FONT_FAMILY, NIGHT


def test_build_stylesheet_balances_its_braces() -> None:
    stylesheet = build_stylesheet()

    assert stylesheet.count("{") == stylesheet.count("}")


def test_build_stylesheet_leaves_no_unformatted_placeholders() -> None:
    assert "{{" not in build_stylesheet()


def test_build_stylesheet_uses_the_theme_tokens() -> None:
    stylesheet = build_stylesheet()

    assert all(token in stylesheet for token in (CLOUD_GOLD, FONT_FAMILY, NIGHT))


def test_build_stylesheet_includes_the_chat_section() -> None:
    assert CHAT_QSS in build_stylesheet()


def test_build_stylesheet_includes_the_settings_section() -> None:
    assert SETTINGS_QSS in build_stylesheet()


def test_build_stylesheet_lets_widgets_opt_into_the_display_face() -> None:
    assert f'*[display="true"] {{ font-family: "{DISPLAY_FONT_FAMILY}"; }}' in build_stylesheet()


@pytest.mark.parametrize(
    "selector",
    [
        "QLabel#HeaderStatus",
        "QLabel#HeaderPageTitle",
        'QLabel#PrivacyBadge[cloud="true"]',
        "QToolButton#HeaderButton",
        "QFrame#UserBubble",
        "QLabel#Thinking",
        "QTextBrowser#AnswerText",
        'QLabel#ToolStepText[status="failed"]',
        "QLabel#ErrorLine",
        "QToolButton#MessageAction",
        "QPushButton#SourceCard",
        "QFrame#ConfirmCard",
        "QPushButton#SuggestionCard",
        "QLabel#EmptyTitle",
        "QPlainTextEdit#ChatInput",
        "QPushButton#SendButton:disabled",
        "QLineEdit#HistorySearch",
        "QPushButton#ConversationRow",
        "QLabel#HistoryEmpty",
        'QPushButton[variant="primary"]',
        'QPushButton[variant="ghost"]',
        'QLabel[role="muted"]',
        'QLabel[role="error"]',
        "QMenu::item:selected",
    ],
)
def test_build_stylesheet_styles_the_widgets_that_opt_in(selector: str) -> None:
    assert selector in build_stylesheet()
