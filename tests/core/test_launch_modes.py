from __future__ import annotations

import sys

import pytest
from pytest_mock import MockerFixture

from core.launch_modes import FAILED_EXIT_CODE, MCP_FLAG, RUN_CODE_FLAG, run_headless, run_headless_mode


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


def test_run_headless_mode_runs_the_mcp_bridge(mocker: MockerFixture) -> None:
    bridge = mocker.patch("core.mcp_server.run_bridge")

    assert run_headless_mode(["Nimbus.exe", MCP_FLAG]) is True
    bridge.assert_called_once()


def test_run_headless_mode_runs_a_code_job(mocker: MockerFixture) -> None:
    mocker.patch("core.code_sandbox.attach_std_streams")
    job = mocker.patch("core.code_sandbox.run_job")

    assert run_headless_mode(["Nimbus.exe", RUN_CODE_FLAG, "job.json"]) is True
    assert job.call_args.args[0].name == "job.json"


def test_run_headless_mode_leaves_a_normal_start_alone() -> None:
    assert run_headless_mode(["Nimbus.exe"]) is False
