from __future__ import annotations

from PyQt6.QtWidgets import QPushButton

from ui.settings.label_roles import set_role, set_variant, styled_label


def test_styled_label_sets_role() -> None:
    assert styled_label("Hi", "muted").property("role") == "muted"


def test_set_role_replaces_role() -> None:
    label = styled_label("Oops", "muted")
    set_role(label, "error")
    assert label.property("role") == "error"


def test_set_variant_sets_variant() -> None:
    button = QPushButton("Next")
    set_variant(button, "primary")
    assert button.property("variant") == "primary"
