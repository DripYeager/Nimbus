"""
Builds the single Qt stylesheet every Nimbus window uses, from the theme tokens. Widgets opt
into a look with setObjectName/setProperty rather than styling themselves inline. Owns QSS
text only; custom-painted pieces live in painting.py.
"""

from __future__ import annotations

from ui.theme.tokens import (
    BORDER,
    CLOUD_BADGE,
    CLOUD_GOLD,
    CLOUD_GOLD_DEEP,
    DANGER,
    ENERGY_ORANGE,
    ENERGY_ORANGE_SOFT,
    FONT_FAMILY,
    LOCAL_BADGE,
    NIGHT,
    RADIUS_BUBBLE,
    RADIUS_CONTROL,
    RADIUS_WINDOW,
    SURFACE,
    SURFACE_HOVER,
    SURFACE_RAISED,
    TEXT,
    TEXT_MUTED,
    TEXT_ON_GOLD,
    TITLE_FONT_FAMILY,
)

_BASE = f"""
* {{ font-family: "{FONT_FAMILY}"; color: {TEXT}; }}
QWidget#NightPanel, QDialog, QWizard, QWizardPage {{ background: {NIGHT}; }}
QToolTip {{ background: {SURFACE_RAISED}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QLabel[role="muted"] {{ color: {TEXT_MUTED}; }}
QLabel[role="title"] {{ font-size: 18px; font-weight: 700; }}
QLabel[role="section"] {{ font-size: 13px; font-weight: 600; color: {CLOUD_GOLD}; }}
QLabel[role="error"] {{ color: {DANGER}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {SURFACE_HOVER}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""

_INPUTS = f"""
QLineEdit, QPlainTextEdit, QSpinBox, QComboBox, QKeySequenceEdit {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS_CONTROL}px;
    padding: 6px 10px; selection-background-color: {ENERGY_ORANGE};
}}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {CLOUD_GOLD}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: none; width: 0; height: 0; border-left: 5px solid transparent;
    border-right: 5px solid transparent; border-top: 6px solid {TEXT_MUTED}; margin-right: 10px; }}
QComboBox QAbstractItemView {{ background: {SURFACE_RAISED}; border: 1px solid {BORDER}; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {BORDER};
    background: {SURFACE}; }}
QCheckBox::indicator:checked {{ background: {CLOUD_GOLD}; border-color: {CLOUD_GOLD_DEEP}; }}
QListWidget {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS_CONTROL}px; }}
QListWidget::item {{ padding: 6px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {SURFACE_HOVER}; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {TEXT_MUTED}; padding: 8px 16px; font-weight: 600; }}
QTabBar::tab:selected {{ color: {CLOUD_GOLD}; border-bottom: 2px solid {CLOUD_GOLD}; }}
QProgressBar {{ background: {SURFACE}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ border-radius: 4px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CLOUD_GOLD}, stop:1 {ENERGY_ORANGE}); }}
"""

_BUTTONS = f"""
QPushButton {{ background: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: {RADIUS_CONTROL}px;
    padding: 7px 14px; font-weight: 600; }}
QPushButton:hover {{ background: {SURFACE_HOVER}; }}
QPushButton:disabled {{ color: {TEXT_MUTED}; }}
QPushButton[variant="primary"] {{ color: {TEXT_ON_GOLD}; border: none;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {CLOUD_GOLD}, stop:1 {ENERGY_ORANGE_SOFT}); }}
QPushButton[variant="primary"]:hover {{ background: {CLOUD_GOLD}; }}
QPushButton[variant="danger"] {{ color: {DANGER}; }}
QPushButton[variant="chip"] {{ background: {SURFACE}; border-radius: 14px; padding: 6px 12px; font-weight: 500;
    color: {TEXT_MUTED}; }}
QPushButton[variant="chip"]:hover {{ color: {TEXT}; border-color: {CLOUD_GOLD}; }}
QToolButton {{ background: transparent; border: none; border-radius: 8px; padding: 4px; }}
QToolButton:hover {{ background: rgba(255, 255, 255, 0.18); }}
"""

_CHAT = f"""
QFrame#ChatPanel {{ background: {NIGHT}; border: 1px solid {BORDER}; border-radius: {RADIUS_WINDOW}px; }}
QLabel#HeaderTitle {{ font-family: "{TITLE_FONT_FAMILY}"; font-size: 17px; color: #FFFFFF; letter-spacing: 2px; }}
QLabel#HeaderStatus {{ color: rgba(255, 255, 255, 0.9); font-size: 11px; }}
QLabel#PrivacyBadge {{ color: #FFFFFF; border-radius: 9px; padding: 2px 9px; font-size: 11px; font-weight: 700; }}
QLabel#PrivacyBadge[cloud="false"] {{ background: {LOCAL_BADGE}; }}
QLabel#PrivacyBadge[cloud="true"] {{ background: {CLOUD_BADGE}; }}
QFrame#UserBubble {{ background: {SURFACE_HOVER}; border-radius: {RADIUS_BUBBLE}px; }}
QLabel#UserText {{ font-size: 14px; }}
QTextBrowser#AnswerText {{ background: transparent; border: none; font-size: 14px; }}
QLabel#ToolChip {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: 3px 9px;
    font-size: 11px; color: {TEXT_MUTED}; }}
QLabel#ToolChip[status="failed"], QLabel#ToolChip[status="denied"] {{ color: {DANGER}; }}
QPushButton#SourceCard {{ text-align: left; background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px;
    padding: 6px 10px; font-weight: 500; }}
QPushButton#SourceCard:hover {{ border-color: {CLOUD_GOLD}; }}
QFrame#ConfirmCard {{ background: {SURFACE_RAISED}; border: 1px solid {CLOUD_GOLD_DEEP}; border-radius: 12px; }}
QLabel#EmptyTitle {{ font-size: 24px; font-weight: 800; color: {CLOUD_GOLD}; }}
QPlainTextEdit#ChatInput {{ background: transparent; border: none; font-size: 14px; padding: 4px; }}
QPushButton#SendButton {{ border: none; border-radius: 17px; font-size: 15px; color: {TEXT_ON_GOLD};
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {CLOUD_GOLD}, stop:1 {ENERGY_ORANGE}); }}
QPushButton#SendButton:disabled {{ background: {SURFACE_RAISED}; color: {TEXT_MUTED}; }}
QLabel#FooterHint {{ color: {TEXT_MUTED}; font-size: 11px; }}
QLabel#ErrorLine {{ color: {DANGER}; }}
QListWidget#HistoryList {{ background: transparent; border: none; font-size: 13px; }}
QScrollArea#ChatScroll, QWidget#ChatContent {{ background: transparent; }}
QToolButton#HeaderButton {{ color: #FFFFFF; font-size: 16px; font-weight: 700; min-width: 30px; min-height: 30px; }}
"""


def build_stylesheet() -> str:
    """The full application stylesheet."""
    return _BASE + _INPUTS + _BUTTONS + _CHAT
