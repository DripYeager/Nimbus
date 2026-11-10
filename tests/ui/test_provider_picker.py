from __future__ import annotations

from unittest.mock import Mock

from ui.settings.provider_picker import LOCAL_PROVIDER, ProviderPicker


def test_provider_picker_provider_defaults_to_local() -> None:
    assert ProviderPicker().provider() == LOCAL_PROVIDER


def test_provider_picker_set_provider_does_not_emit_picked() -> None:
    picker = ProviderPicker()
    picked = Mock()
    picker.picked.connect(picked)
    picker.set_provider("anthropic")
    assert picker.provider() == "anthropic"
    picked.assert_not_called()


def test_provider_picker_pick_emits_picked() -> None:
    picker = ProviderPicker()
    picked = Mock()
    picker.picked.connect(picked)
    picker.pick("openai")
    picked.assert_called_once_with("openai")
