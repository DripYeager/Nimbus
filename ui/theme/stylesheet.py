"""
Builds the single Qt stylesheet every Nimbus window uses, from the theme tokens: shared base,
inputs and buttons here, plus the chat and Settings sections from their own modules. Widgets opt
into a look with setObjectName/setProperty rather than styling themselves inline. QSS text only;
custom-painted pieces live in painting.py, energy.py and backdrop.py.
"""

from __future__ import annotations

from config.paths import asset_path
from ui.theme.chat_styles import CHAT_QSS
from ui.theme.settings_styles import SETTINGS_QSS
from ui.theme.tokens import (
    BORDER,
    BORDER_STRONG,
    CLOUD_GOLD,
    DANGER,
    DISPLAY_FONT_FAMILY,
    FONT_FAMILY,
    GI_ORANGE,
    GI_ORANGE_DEEP,
    NIGHT,
    RADIUS_CONTROL,
    SURFACE,
    SURFACE_HOVER,
    SURFACE_RAISED,
    TEXT,
    TEXT_FAINT,
    TEXT_MUTED,
    TEXT_ON_ORANGE,
)

# QSS needs a file for the dropdown arrow; this copy is pre-tinted to TEXT_MUTED.
_CHEVRON = asset_path("icons", "chevron-down-muted.svg").as_posix()

_BASE = f"""
* {{ font-family: "{FONT_FAMILY}"; color: {TEXT}; }}
*[display="true"] {{ font-family: "{DISPLAY_FONT_FAMILY}"; }}
QWidget#NightPanel, QDialog, QWizard, QWizardPage {{ background: {NIGHT}; }}
QToolTip {{ background: {SURFACE_RAISED}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; padding: 6px 8px;
    border-radius: 8px; }}
QLabel[role="muted"] {{ color: {TEXT_MUTED}; }}
QLabel[role="faint"] {{ color: {TEXT_FAINT}; }}
QLabel[role="title"] {{ font-size: 18px; font-weight: 700; }}
QLabel[role="section"] {{ font-size: 13px; font-weight: 600; color: {CLOUD_GOLD}; }}
QLabel[role="error"] {{ color: {DANGER}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: rgba(255, 255, 255, 0.10); border-radius: 3px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255, 255, 255, 0.22); }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0;
    background: none; }}
QMenu {{ background: {SURFACE_RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: 12px; padding: 6px; }}
QMenu::item {{ padding: 8px 18px; border-radius: 8px; }}
QMenu::item:selected {{ background: {SURFACE_HOVER}; }}
QMenu::item:disabled {{ color: {TEXT_MUTED}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 6px 8px; }}
"""

_INPUTS = f"""
QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QKeySequenceEdit {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS_CONTROL}px;
    padding: 8px 12px; selection-background-color: {GI_ORANGE}; selection-color: {TEXT_ON_ORANGE};
}}
QLineEdit:hover, QPlainTextEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover,
QComboBox:hover {{ border-color: {BORDER_STRONG}; }}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus {{ border: 1px solid {GI_ORANGE}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url("{_CHEVRON}"); width: 14px; height: 14px; margin-right: 10px; }}
QComboBox QAbstractItemView {{ background: {SURFACE_RAISED}; border: 1px solid {BORDER_STRONG};
    selection-background-color: {SURFACE_HOVER}; outline: none; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 6px; border: 1px solid {BORDER_STRONG};
    background: {SURFACE}; }}
QCheckBox::indicator:checked {{ background: {GI_ORANGE}; border-color: {GI_ORANGE_DEEP}; }}
QListWidget {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS_CONTROL}px; outline: none; }}
QListWidget::item {{ padding: 8px; border-radius: 8px; }}
QListWidget::item:selected {{ background: {SURFACE_HOVER}; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {TEXT_MUTED}; padding: 8px 16px; font-weight: 600; }}
QTabBar::tab:selected {{ color: {GI_ORANGE}; border-bottom: 2px solid {GI_ORANGE}; }}
QProgressBar {{ background: {SURFACE}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ border-radius: 4px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CLOUD_GOLD}, stop:1 {GI_ORANGE}); }}
"""

_BUTTONS = f"""
QPushButton {{ background: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: {RADIUS_CONTROL}px;
    padding: 8px 16px; font-weight: 600; }}
QPushButton:hover {{ background: {SURFACE_HOVER}; border-color: {BORDER_STRONG}; }}
QPushButton:pressed {{ background: {SURFACE}; }}
QPushButton:disabled {{ color: {TEXT_FAINT}; }}
QPushButton[variant="primary"] {{ color: {TEXT_ON_ORANGE}; border: none;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {CLOUD_GOLD}, stop:1 {GI_ORANGE}); }}
QPushButton[variant="primary"]:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 #FFD866, stop:1 #FF9A3C); }}
QPushButton[variant="primary"]:disabled {{ background: {SURFACE_HOVER}; color: {TEXT_FAINT}; }}
QPushButton[variant="ghost"] {{ background: transparent; border: 1px solid transparent; color: {TEXT_MUTED}; }}
QPushButton[variant="ghost"]:hover {{ background: rgba(255, 255, 255, 0.06); color: {TEXT}; }}
QPushButton[variant="danger"] {{ color: {DANGER}; }}
QPushButton[variant="chip"] {{ background: {SURFACE}; border-radius: 16px; padding: 7px 14px; font-weight: 500;
    color: {TEXT_MUTED}; }}
QPushButton[variant="chip"]:hover {{ color: {TEXT}; border-color: {GI_ORANGE}; }}
QToolButton {{ background: transparent; border: none; border-radius: 10px; padding: 6px; }}
QToolButton:hover {{ background: rgba(255, 255, 255, 0.10); }}
QToolButton:pressed {{ background: rgba(255, 255, 255, 0.06); }}
"""


def build_stylesheet() -> str:
    """The full application stylesheet."""
    return _BASE + _INPUTS + _BUTTONS + CHAT_QSS + SETTINGS_QSS
