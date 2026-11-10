"""
The stylesheet rules for the Settings page and onboarding: the navigation rail, cards, folder
rows, file-type chips, provider cards, badges, the status pill, the keycap hotkey field and the
wizard's footer. Built from the theme tokens and appended to the app stylesheet; owns QSS text
only, matched through the object names and properties those screens set.
"""

from __future__ import annotations

from ui.theme.tokens import (
    BORDER,
    BORDER_STRONG,
    CLOUD_GOLD,
    DANGER,
    GI_ORANGE,
    GI_ORANGE_DEEP,
    LOCAL_BADGE,
    MONO_FONT_FAMILY,
    NIGHT,
    RADIUS_CARD,
    SCOUTER_GREEN,
    SUCCESS,
    SURFACE,
    SURFACE_RAISED,
    TEXT,
    TEXT_MUTED,
    TEXT_ON_ORANGE,
)

_STRUCTURE = f"""
QWidget#SettingsPage {{ background: transparent; }}
QFrame#SettingsRail {{ background: transparent; border: none; border-right: 1px solid {BORDER}; }}
QPushButton#NavItem {{ text-align: left; background: transparent; border: none; border-radius: 10px;
    padding: 10px 12px; color: {TEXT_MUTED}; font-size: 13px; font-weight: 600; }}
QPushButton#NavItem:hover {{ background: rgba(255, 255, 255, 0.05); color: {TEXT}; }}
QPushButton#NavItem:checked {{ background: {SURFACE_RAISED}; color: {TEXT};
    border-left: 3px solid {GI_ORANGE}; padding-left: 9px; }}
QFrame#SettingsBar {{ background: {SURFACE}; border: none; border-top: 1px solid {BORDER}; }}
QLabel#BarStatus {{ color: {TEXT_MUTED}; }}
QLabel#BarStatus[state="success"] {{ color: {SUCCESS}; font-weight: 600; }}
QLabel#BarStatus[state="error"] {{ color: {DANGER}; }}
QLabel#SectionTitle {{ color: {CLOUD_GOLD}; }}
QLabel#GroupTitle {{ color: {TEXT}; font-size: 14px; font-weight: 700; }}
QLabel#RowTitle {{ color: {TEXT}; font-size: 13px; font-weight: 600; }}
QFrame#Card, QFrame#IndexCard {{ background: {SURFACE}; border: 1px solid {BORDER};
    border-radius: {RADIUS_CARD}px; }}
QFrame#PrivacyCard {{ background: rgba(62, 240, 138, 0.05); border: 1px solid rgba(62, 240, 138, 0.22);
    border-radius: {RADIUS_CARD}px; }}
QFrame#PrivacyCard[state="cloud"] {{ background: rgba(255, 138, 31, 0.06); border-color: rgba(255, 138, 31, 0.30); }}
QFrame#CardDivider {{ background: {BORDER}; border: none; }}
QLabel#IconTile {{ background: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 10px; }}
"""

_SOURCES = f"""
QFrame#FolderRow {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS_CARD}px; }}
QFrame#FolderRow:hover {{ border-color: {BORDER_STRONG}; }}
QPushButton#IconButton {{ background: transparent; border: none; border-radius: 8px; padding: 0; }}
QPushButton#IconButton:hover {{ background: rgba(255, 90, 106, 0.12); }}
QPushButton#AddFolderButton {{ background: transparent; border: 1px dashed {BORDER_STRONG};
    border-radius: {RADIUS_CARD}px; padding: 12px; color: {TEXT_MUTED}; font-weight: 600; }}
QPushButton#AddFolderButton:hover {{ border-color: {GI_ORANGE}; color: {TEXT}; background: rgba(255, 138, 31, 0.06); }}
QPushButton#TypeChip {{ background: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 16px;
    padding: 0 12px; color: {TEXT_MUTED}; font-weight: 600; text-align: left; }}
QPushButton#TypeChip:hover {{ border-color: {GI_ORANGE}; color: {TEXT}; }}
QPushButton#TypeChip:checked {{ color: {TEXT_ON_ORANGE}; border-color: {GI_ORANGE_DEEP};
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFA347, stop:1 {GI_ORANGE}); }}
"""

_MODEL = f"""
QPushButton#ProviderCard {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS_CARD}px;
    padding: 0; text-align: left; }}
QPushButton#ProviderCard:hover {{ background: {SURFACE_RAISED}; border-color: {BORDER_STRONG}; }}
QPushButton#ProviderCard:checked {{ background: {SURFACE_RAISED}; border: 2px solid {GI_ORANGE}; }}
QLabel#Badge {{ border-radius: 9px; padding: 2px 8px; font-size: 11px; font-weight: 700; }}
QLabel#Badge[tone="local"] {{ color: {SCOUTER_GREEN}; background: rgba(31, 175, 107, 0.16);
    border: 1px solid {LOCAL_BADGE}; }}
QLabel#Badge[tone="cloud"] {{ color: {GI_ORANGE}; background: rgba(255, 138, 31, 0.12);
    border: 1px solid rgba(255, 138, 31, 0.55); }}
QFrame#StatusPill {{ border-radius: 14px; background: {SURFACE_RAISED}; border: 1px solid {BORDER}; }}
QFrame#StatusPill[state="ok"] {{ background: rgba(62, 224, 138, 0.10); border-color: rgba(62, 224, 138, 0.45); }}
QFrame#StatusPill[state="error"] {{ background: rgba(255, 90, 106, 0.10); border-color: rgba(255, 90, 106, 0.45); }}
QLabel#StatusPillText {{ color: {TEXT_MUTED}; font-size: 12px; font-weight: 600; }}
QLabel#StatusPillText[state="ok"] {{ color: {SUCCESS}; }}
QLabel#StatusPillText[state="error"] {{ color: {DANGER}; }}
"""

_GENERAL = f"""
QKeySequenceEdit#Keycap {{ background: transparent; border: none; padding: 0; }}
QKeySequenceEdit#Keycap QLineEdit {{ font-family: "{MONO_FONT_FAMILY}"; font-size: 14px; font-weight: 700;
    color: {CLOUD_GOLD}; background: {SURFACE_RAISED}; border: 1px solid {BORDER_STRONG};
    border-bottom: 3px solid {BORDER_STRONG}; border-radius: 10px; padding: 6px 12px;
    qproperty-alignment: AlignCenter; }}
QKeySequenceEdit#Keycap QLineEdit:focus {{ border-color: {GI_ORANGE}; border-bottom-color: {GI_ORANGE_DEEP}; }}
QWidget#SettingsPanel QSpinBox, QWidget#OnboardingWindow QSpinBox {{ qproperty-alignment: AlignRight; }}
"""

_ONBOARDING = f"""
QWidget#OnboardingWindow {{ background: {NIGHT}; }}
QFrame#WizardFooter {{ background: {SURFACE}; border: none; border-top: 1px solid {BORDER}; }}
QLabel#HeroTitle {{ color: {CLOUD_GOLD}; }}
QLabel#StepCaption {{ color: {TEXT_MUTED}; font-size: 12px; font-weight: 600; }}
QWidget#OnboardingStep {{ background: transparent; }}
"""

_PROGRESS = f"""
QProgressBar#FolderProgress {{ background: rgba(255, 255, 255, 0.08); border: none; border-radius: 2px; }}
QProgressBar#FolderProgress::chunk {{ border-radius: 2px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CLOUD_GOLD}, stop:1 {GI_ORANGE}); }}
QFrame#Card[accent="orange"] {{ border-left: 3px solid {GI_ORANGE}; }}
"""

SETTINGS_QSS = _STRUCTURE + _SOURCES + _MODEL + _GENERAL + _ONBOARDING + _PROGRESS
