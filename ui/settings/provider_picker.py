"""
The four model providers as selectable cards in a 2×2 grid, each with an icon, a one-line
description and a local/cloud badge. Owns showing and picking a provider; what a pick means
(the cloud warning, which fields to show) is ModelEditor's job.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from models.chat import ProviderName
from ui.settings.label_roles import styled_label
from ui.settings.section_layout import CARD_PADDING, CARD_ROW_SPACING, GAP, icon_tile
from ui.theme.tokens import GI_ORANGE, SCOUTER_GREEN

LOCAL_PROVIDER: ProviderName = "ollama"
# (name, description, icon) per provider, in grid order.
PROVIDER_CARDS: dict[ProviderName, tuple[str, str, str]] = {
    "ollama": ("Ollama", "Runs on this PC. Nothing leaves it.", "hard-drive"),
    "openai": ("OpenAI", "GPT models, over the internet.", "sparkles"),
    "anthropic": ("Anthropic", "Claude models, over the internet.", "message-square"),
    "openai_compatible": ("Custom server", "Any OpenAI-compatible endpoint.", "globe"),
}
LOCAL_BADGE_TEXT = "Local · private"
CLOUD_BADGE_TEXT = "Cloud"
GRID_COLUMNS = 2
CARD_MIN_HEIGHT = 112
GLOW_BLUR = 28
GLOW_ALPHA = 110


def _badge(is_local: bool) -> QLabel:
    badge = QLabel(LOCAL_BADGE_TEXT if is_local else CLOUD_BADGE_TEXT)
    badge.setObjectName("Badge")
    badge.setProperty("tone", "local" if is_local else "cloud")
    return badge


def _glow() -> QGraphicsDropShadowEffect:
    """The soft orange halo around the selected card."""
    color = QColor(GI_ORANGE)
    color.setAlpha(GLOW_ALPHA)
    effect = QGraphicsDropShadowEffect()
    effect.setBlurRadius(GLOW_BLUR)
    effect.setOffset(0, 0)
    effect.setColor(color)
    return effect


class _ProviderCard(QPushButton):
    """A checkable card; the labels inside let clicks fall through to the button."""

    def __init__(self, provider: ProviderName, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProviderCard")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(CARD_MIN_HEIGHT)
        self._glow = _glow()
        self._glow.setEnabled(False)
        self.setGraphicsEffect(self._glow)
        self._build_layout(provider)
        self.toggled.connect(self._glow.setEnabled)

    def _build_layout(self, provider: ProviderName) -> None:
        """Icon and badge on top, then the name and its description."""
        name, description, icon = PROVIDER_CARDS[provider]
        is_local = provider == LOCAL_PROVIDER
        top = QHBoxLayout()
        top.addWidget(icon_tile(icon, SCOUTER_GREEN if is_local else GI_ORANGE))
        top.addStretch(1)
        top.addWidget(_badge(is_local), 0, Qt.AlignmentFlag.AlignTop)
        title = QLabel(name)
        title.setObjectName("RowTitle")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        layout.setSpacing(GAP // 2)
        layout.addLayout(top)
        layout.addSpacing(GAP // 2)
        layout.addWidget(title)
        layout.addWidget(styled_label(description, "muted"))
        for child in self.findChildren(QLabel):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


class ProviderPicker(QWidget):
    """Emits picked(provider) when the user clicks a card; set_provider() changes it silently."""

    picked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cards = {provider: _ProviderCard(provider) for provider in PROVIDER_CARDS}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(CARD_ROW_SPACING)
        for index, (provider, card) in enumerate(self._cards.items()):
            self._group.addButton(card)
            grid.addWidget(card, index // GRID_COLUMNS, index % GRID_COLUMNS)
            card.clicked.connect(lambda _=False, name=provider: self.picked.emit(name))

    def provider(self) -> ProviderName:
        """The provider whose card is selected (the local one before anything is set)."""
        return next((name for name, card in self._cards.items() if card.isChecked()), LOCAL_PROVIDER)

    def set_provider(self, provider: ProviderName) -> None:
        """Selects provider's card without emitting picked."""
        self._cards[provider].setChecked(True)

    def pick(self, provider: ProviderName) -> None:
        """Selects provider's card as if the user had clicked it."""
        self._cards[provider].click()
