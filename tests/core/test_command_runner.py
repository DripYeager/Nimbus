from __future__ import annotations

import sys

import pytest

from core.command_runner import run_powershell, trim_output

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Runs Windows PowerShell")


@windows_only
def test_run_powershell_returns_what_the_command_printed() -> None:
    result = run_powershell("Write-Output 'hello from nimbus'")

    assert (result.exit_code, result.output, result.timed_out) == (0, "hello from nimbus", False)


@windows_only
def test_run_powershell_keeps_unicode_intact() -> None:
    assert run_powershell("Write-Output 'café ✓'").output == "café ✓"


@windows_only
def test_run_powershell_stops_a_command_that_runs_too_long() -> None:
    result = run_powershell("Start-Sleep -Seconds 20; Write-Output done", timeout_s=2)

    assert (result.timed_out, "done" in result.output) == (True, False)


@windows_only
def test_run_powershell_reports_errors_in_the_output() -> None:
    result = run_powershell("Get-Item C:\\definitely\\not\\here")

    assert "Cannot find path" in result.output


def test_trim_output_keeps_short_text_whole() -> None:
    assert trim_output("one\ntwo   \n\n") == "one\ntwo"


def test_trim_output_keeps_the_start_and_end_of_long_text() -> None:
    text = "A" * 5000 + "B" * 5000

    trimmed = trim_output(text, limit=1000, tail=200)

    assert trimmed.startswith("A" * 800) and trimmed.endswith("B" * 200) and "characters cut" in trimmed
