from __future__ import annotations

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from core.exceptions import ProviderError
from core.service_container import AppServices


@pytest.fixture
def services(mocker: MockerFixture) -> AppServices:
    built = AppServices()
    built.index = mocker.Mock()
    built.watcher = mocker.Mock()
    built.provider = mocker.Mock()
    return built


def test_apply_settings_still_applies_folders_and_listeners_when_the_provider_refuses(
    services: AppServices, mocker: MockerFixture
) -> None:
    listener = mocker.Mock()
    services.add_settings_listener(listener)
    services.provider.reload.side_effect = ProviderError("needs a base URL")

    with pytest.raises(ProviderError):
        services.apply_settings()

    services.index.apply_settings.assert_called_once()
    services.watcher.restart.assert_called_once()
    listener.assert_called_once()


def test_is_path_shared_accepts_a_path_inside_a_source(services: AppServices, tmp_path: Path) -> None:
    services.index.rules.is_covered.return_value = True

    assert services.is_path_shared(tmp_path / "report.pdf")


def test_is_path_shared_rejects_a_path_outside_every_source(services: AppServices, tmp_path: Path) -> None:
    services.index.rules.is_covered.return_value = False

    assert not services.is_path_shared(tmp_path / "secret.txt")
