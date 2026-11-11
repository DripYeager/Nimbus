from __future__ import annotations

import sys

import pytest
from pytest_mock import MockerFixture

import main
from main import FAILED_EXIT_CODE, run_headless


def _fail() -> None:
    raise RuntimeError("broken")


def test_run_headless_turns_an_error_into_exit_code_one(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        run_headless(_fail)

    assert stopped.value.code == FAILED_EXIT_CODE
    assert "RuntimeError: broken" in capsys.readouterr().err


def test_run_headless_keeps_the_jobs_own_exit_code() -> None:
    def finish() -> None:
        sys.exit(3)

    with pytest.raises(SystemExit) as stopped:
        run_headless(finish)

    assert stopped.value.code == 3


def test_run_headless_with_no_stderr_still_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stderr", None)

    with pytest.raises(SystemExit) as stopped:
        run_headless(_fail)

    assert stopped.value.code == FAILED_EXIT_CODE


def test_main_with_mcp_flag_runs_the_bridge(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = mocker.patch("core.mcp_server.run_bridge")
    monkeypatch.setattr(sys, "argv", ["Nimbus.exe", main.MCP_FLAG])

    main.main()

    bridge.assert_called_once()


def test_main_with_run_code_flag_runs_the_job(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    mocker.patch("core.code_sandbox.attach_std_streams")
    job = mocker.patch("core.code_sandbox.run_job")
    monkeypatch.setattr(sys, "argv", ["Nimbus.exe", main.RUN_CODE_FLAG, "job.json"])

    main.main()

    assert job.call_args.args[0].name == "job.json"


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
