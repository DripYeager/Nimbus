"""
Small helpers for the stylesheet's label roles (title, section, muted, error) and button
variants, used across the settings and onboarding screens. Owns assigning them only; the look
itself lives in the theme.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QWidget


def styled_label(text: str, role: str | None = None, *, wrap: bool = False) -> QLabel:
    """A QLabel already tagged with a stylesheet role."""
    label = QLabel(text)
    label.setWordWrap(wrap)
    if role:
        label.setProperty("role", role)
    return label


def set_role(widget: QWidget, role: str) -> None:
    """Changes a widget's role after it has been shown."""
    _restyle(widget, "role", role)


def set_variant(widget: QWidget, variant: str) -> None:
    """Changes a button's variant after it has been polished."""
    _restyle(widget, "variant", variant)


def _restyle(widget: QWidget, name: str, value: str) -> None:
    """Qt only re-reads dynamic properties in selectors on a re-polish."""
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
