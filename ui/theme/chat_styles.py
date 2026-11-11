"""
The chat window's slice of the stylesheet: header, messages, cards, composer and history.
QSS text only, selectors match the object names and properties the chat widgets set.
"""

from __future__ import annotations

from ui.theme.tokens import (
    BORDER,
    BORDER_STRONG,
    CLOUD_BADGE,
    CLOUD_GOLD,
    DANGER,
    GI_ORANGE,
    LOCAL_BADGE,
    MONO_FONT_FAMILY,
    NIGHT_DEEP,
    RADIUS_BUBBLE,
    RADIUS_CARD,
    SUCCESS,
    SURFACE,
    SURFACE_HOVER,
    SURFACE_RAISED,
    TEXT,
    TEXT_FAINT,
    TEXT_MUTED,
    TEXT_ON_ORANGE,
)

_HEADER = f"""
QLabel#HeaderStatus {{ color: rgba(255, 255, 255, 0.88); font-size: 12px; }}
QLabel#HeaderPageTitle, QLabel#HeaderWordmark {{ color: #FFFFFF; }}
QLabel#PrivacyBadge {{ color: #FFFFFF; border-radius: 12px; padding: 0 12px; font-size: 11px;
    font-weight: 700; }}
QLabel#PrivacyBadge[cloud="false"] {{ background: {LOCAL_BADGE}; }}
QLabel#PrivacyBadge[cloud="true"] {{ background: {CLOUD_BADGE}; }}
QToolButton#HeaderButton {{ border-radius: 12px; padding: 7px; }}
QToolButton#HeaderButton:hover {{ background: rgba(255, 255, 255, 0.20); }}
"""

_MESSAGES = f"""
QWidget#ChatContent {{ background: transparent; }}
QFrame#UserBubble {{ border-top-left-radius: {RADIUS_BUBBLE}px; border-top-right-radius: {RADIUS_BUBBLE}px;
    border-bottom-left-radius: {RADIUS_BUBBLE}px; border-bottom-right-radius: 6px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFB347, stop:1 {GI_ORANGE}); }}
QLabel#UserText {{ font-size: 14px; color: {TEXT_ON_ORANGE}; }}
QLabel#ReplyAuthor {{ font-size: 12px; font-weight: 700; color: {TEXT}; }}
QLabel#ReplyMeta {{ font-size: 11px; color: {TEXT_FAINT}; }}
QLabel#Thinking {{ font-size: 13px; color: {CLOUD_GOLD}; }}
QTextBrowser#AnswerText {{ background: transparent; border: none; font-size: 14px; color: {TEXT}; }}
QLabel#ToolStepText {{ font-size: 12px; color: {TEXT_MUTED}; }}
QLabel#ToolStepText[status="failed"], QLabel#ToolStepText[status="denied"] {{ color: {DANGER}; }}
QLabel#ErrorLine {{ color: {DANGER}; font-size: 13px; }}
QToolButton#MessageAction {{ border-radius: 8px; padding: 4px; }}
QToolButton#MicButton {{ border: none; background: transparent; border-radius: 16px; padding: 7px; }}
QToolButton#MicButton:hover {{ background: {SURFACE_HOVER}; }}
"""

_CARDS = f"""
QPushButton#SourceCard {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px;
    padding: 0; text-align: left; }}
QPushButton#SourceCard:hover {{ background: {SURFACE_RAISED}; border-color: {GI_ORANGE}; }}
QLabel#SourceName {{ font-size: 13px; font-weight: 600; }}
QLabel#SourceFolder {{ font-size: 11px; color: {TEXT_FAINT}; }}
QFrame#ConfirmCard {{ background: {SURFACE_RAISED}; border: 1px solid {BORDER_STRONG};
    border-left: 3px solid {GI_ORANGE}; border-radius: {RADIUS_CARD}px; }}
QLabel#ConfirmTitle {{ font-size: 12px; font-weight: 700; color: {GI_ORANGE}; letter-spacing: 0.5px; }}
QLabel#ConfirmText {{ font-size: 14px; }}
QToolButton#DeleteChat {{ color: {DANGER}; font-weight: 700; }}
QPushButton#BubbleLink {{ background: transparent; border: none; padding: 0; font-size: 12px;
    font-weight: 700; color: {TEXT_ON_ORANGE}; text-decoration: underline; }}
QFrame#ConfirmCard[answered="allowed"] {{ border-left: 3px solid {SUCCESS}; background: {SURFACE}; }}
QFrame#ConfirmCard[answered="declined"] {{ border-left: 3px solid {DANGER}; background: {SURFACE}; }}
QFrame#ConfirmCard[answered="allowed"] QLabel#ConfirmTitle {{ color: {SUCCESS}; }}
QFrame#ConfirmCard[answered="declined"] QLabel#ConfirmTitle {{ color: {DANGER}; }}
QFrame#ConfirmCard[answered="skipped"] {{ border-left: 3px solid {BORDER_STRONG}; background: {SURFACE}; }}
QFrame#ConfirmCard[answered="skipped"] QLabel#ConfirmTitle {{ color: {TEXT_MUTED}; }}
QFrame#CodeBlock {{ background: {NIGHT_DEEP}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#CodeBlock:hover {{ border-color: {BORDER_STRONG}; }}
QLabel#CodeTitle {{ font-size: 11px; font-weight: 700; color: {TEXT_MUTED}; letter-spacing: 0.5px; }}
QLabel#CodeText {{ font-family: "{MONO_FONT_FAMILY}", Consolas; font-size: 12px; color: {TEXT}; }}
QPushButton#CodeLink {{ background: transparent; border: none; padding: 0 2px; font-size: 11px;
    font-weight: 600; color: {CLOUD_GOLD}; }}
QPushButton#CodeLink:hover {{ color: {GI_ORANGE}; }}
QPushButton#SuggestionCard {{ background: rgba(17, 26, 46, 0.85); border: 1px solid {BORDER}; border-radius: 14px;
    padding: 12px 14px; text-align: left; font-weight: 500; color: {TEXT}; }}
QPushButton#SuggestionCard:hover {{ border-color: {GI_ORANGE}; background: {SURFACE_RAISED}; }}
QPushButton#AttachmentOffer, QPushButton#AttachmentSuggestion {{ background: {SURFACE}; border: 1px solid {BORDER};
    border-radius: 13px; padding: 5px 12px; color: {TEXT}; font-size: 12px; }}
QPushButton#AttachmentOffer:hover, QPushButton#AttachmentSuggestion:hover {{ border-color: {GI_ORANGE}; }}
QPushButton#AttachmentPill, QPushButton#AttachmentPill:disabled {{ background: {SURFACE_RAISED};
    border: 1px solid {GI_ORANGE}; border-radius: 13px; padding: 5px 12px; color: {CLOUD_GOLD};
    font-size: 12px; font-weight: 600; }}
QLabel#AttachmentTag {{ color: {TEXT_ON_ORANGE}; font-size: 12px; font-weight: 600; }}
QLabel#EmptyTitle {{ color: {CLOUD_GOLD}; }}
QLabel#EmptySubtitle {{ font-size: 14px; color: {TEXT_MUTED}; }}
"""

_COMPOSER = f"""
QPlainTextEdit#ChatInput {{ background: transparent; border: none; font-size: 14px; padding: 6px 2px; }}
QPushButton#SendButton {{ border: none; border-radius: 19px; padding: 0;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {CLOUD_GOLD}, stop:1 {GI_ORANGE}); }}
QPushButton#SendButton:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFD866,
    stop:1 #FF9A3C); }}
QPushButton#SendButton:disabled {{ background: {SURFACE_HOVER}; }}
QLabel#StoppedLine {{ color: {TEXT_FAINT}; font-size: 12px; font-style: italic; }}
QLabel#FooterHint {{ color: {TEXT_FAINT}; font-size: 11px; }}
"""

_HISTORY = f"""
QLineEdit#HistorySearch {{ border-radius: 14px; padding: 9px 14px 9px 6px; }}
QPushButton#ConversationRow {{ background: transparent; border: 1px solid transparent; border-radius: 12px;
    padding: 0; text-align: left; }}
QPushButton#ConversationRow:hover {{ background: {SURFACE}; border-color: {BORDER}; }}
QLabel#ConversationTitle {{ font-size: 14px; font-weight: 600; }}
QLabel#ConversationDate {{ font-size: 11px; color: {TEXT_FAINT}; }}
QLabel#HistoryEmpty {{ font-size: 14px; color: {TEXT_MUTED}; }}
"""

CHAT_QSS = _HEADER + _MESSAGES + _CARDS + _COMPOSER + _HISTORY
