from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from core.exceptions import AutostartError, NimbusError
from models.api import SettingsView
from ui.api_client import ApiClient
from ui.onboarding.onboarding_wizard import OnboardingWizard

VALUES: dict[str, Any] = {
    "sources": [{"path": "C:/Users/me/Documents", "include_contents": True}],
    "file_categories": ["pdfs"],
    "max_file_size_mb": 50,
    "exclude_patterns": [],
    "llm_provider": "ollama",
    "ollama_host": "http://localhost:11434",
    "ollama_model": "llama3.1:8b",
    "openai_model": "gpt-5-mini",
    "anthropic_model": "claude-haiku-5-5",
    "compatible_model": "",
    "compatible_base_url": "",
    "hotkey": "<ctrl>+<space>",
}


def _run_now(fn: Any, ok: Any, err: Any = None) -> None:
    try:
        result = fn()
    except NimbusError as e:
        if err is not None:
            err(str(e))
        return
    ok(result)


@pytest.fixture
def api(mocker: MockerFixture) -> Mock:
    for module in ("ui.onboarding.onboarding_wizard", "ui.settings.sources_editor", "ui.settings.model_editor"):
        mocker.patch(f"{module}.run_in_background", side_effect=_run_now)
    fake = mocker.Mock(spec=ApiClient)
    fake.settings.return_value = SettingsView(values=VALUES, has_api_key={}, data_dir="C:/data", is_cloud=False)
    fake.source_summaries.return_value = []
    return fake


@pytest.fixture
def autostart(mocker: MockerFixture) -> Mock:
    return mocker.patch("ui.onboarding.onboarding_wizard.apply_autostart")


@pytest.fixture
def wizard(api: Mock, autostart: Mock) -> Iterator[OnboardingWizard]:
    dialog = OnboardingWizard(api)
    dialog.show()
    yield dialog
    dialog.close()


def test_collect_includes_every_page_and_marks_complete(wizard: OnboardingWizard) -> None:
    updates, key = wizard.collect()
    assert updates == {**VALUES, "onboarding_complete": True}
    assert key is None


def test_accept_saves_applies_autostart_and_emits_completed(
    wizard: OnboardingWizard, api: Mock, autostart: Mock
) -> None:
    completed = Mock()
    wizard.completed.connect(completed)
    wizard.accept()
    api.update_settings.assert_called_once_with({**VALUES, "onboarding_complete": True})
    autostart.assert_called_once_with(True)
    completed.assert_called_once()
    assert not wizard.isVisible()


def test_accept_stores_new_api_key(wizard: OnboardingWizard, api: Mock, mocker: MockerFixture) -> None:
    mocker.patch.object(wizard._model, "collect", return_value=({"llm_provider": "anthropic"}, "sk-ant"))
    mocker.patch.object(wizard._model, "provider", return_value="anthropic")
    wizard.accept()
    api.set_api_key.assert_called_once_with("anthropic", "sk-ant")


def test_accept_error_keeps_wizard_open(wizard: OnboardingWizard, api: Mock, mocker: MockerFixture) -> None:
    warning = mocker.patch("ui.onboarding.onboarding_wizard.QMessageBox.warning")
    api.update_settings.side_effect = NimbusError("Couldn't save settings.")
    completed = Mock()
    wizard.completed.connect(completed)
    wizard.accept()
    warning.assert_called_once()
    completed.assert_not_called()
    assert wizard.isVisible()


def test_accept_completes_even_when_autostart_fails(
    wizard: OnboardingWizard, autostart: Mock, mocker: MockerFixture
) -> None:
    warning = mocker.patch("ui.onboarding.onboarding_wizard.QMessageBox.warning")
    autostart.side_effect = AutostartError("Startup folder is locked")
    completed = Mock()
    wizard.completed.connect(completed)
    wizard.accept()
    warning.assert_called_once()
    completed.assert_called_once()


def test_wizard_has_five_steps(wizard: OnboardingWizard) -> None:
    assert wizard.step_count() == 5


def test_advance_moves_to_next_step(wizard: OnboardingWizard) -> None:
    wizard._advance()
    assert wizard.current_step() == 1
    assert wizard._progress.current_step() == 1


def test_go_to_first_step_hides_back(wizard: OnboardingWizard) -> None:
    wizard._go_to(0)
    assert wizard._back_button.isHidden()


def test_go_to_last_step_offers_finish(wizard: OnboardingWizard) -> None:
    wizard._go_to(wizard.step_count() - 1)
    assert wizard._next_button.text() == "Finish"


def test_advance_on_last_step_saves(wizard: OnboardingWizard, api: Mock) -> None:
    wizard._go_to(wizard.step_count() - 1)
    wizard._advance()
    api.update_settings.assert_called_once()
