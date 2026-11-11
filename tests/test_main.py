from __future__ import annotations

import sys

import pytest
from pytest_mock import MockerFixture

import main


def test_main_runs_a_headless_mode_without_starting_the_app(
    mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    mocker.patch("core.launch_modes.run_headless_mode", return_value=True)
    runtime = mocker.patch("core.app_runtime.AppRuntime")
    monkeypatch.setattr(sys, "argv", ["Nimbus.exe", "--mcp"])

    main.main()

    runtime.assert_not_called()


def test_main_hands_over_to_a_running_nimbus_without_starting(
    mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    notify = mocker.patch("ui.single_instance.notify_running_instance", return_value=True)
    runtime = mocker.patch("core.app_runtime.AppRuntime")
    monkeypatch.setattr(sys, "argv", ["Nimbus.exe", "--ask", r"C:\Docs\report.pdf"])

    main.main()

    notify.assert_called_once_with(r"C:\Docs\report.pdf")
    runtime.assert_not_called()


def test_main_starts_when_no_nimbus_is_running(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    mocker.patch("ui.single_instance.notify_running_instance", return_value=False)
    runtime = mocker.patch("core.app_runtime.AppRuntime")
    runtime.return_value.start.return_value = 0
    monkeypatch.setattr(sys, "argv", ["Nimbus.exe"])

    with pytest.raises(SystemExit):
        main.main()

    runtime.return_value.start.assert_called_once()
