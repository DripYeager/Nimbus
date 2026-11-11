from __future__ import annotations

from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from core.command_policy import ELEVATION_MESSAGE
from core.command_runner import CommandResult
from core.exceptions import ToolError
from tools.registry import ToolRegistry
from tools.terminal_tools import TerminalToolbox, describe_command, describe_result, needs_approval


@pytest.fixture
def runner(mocker: MockerFixture) -> Mock:
    return mocker.patch(
        "tools.terminal_tools.run_powershell", return_value=CommandResult(exit_code=0, output="IPv4 Address: 10.0.0.5")
    )


def test_run_command_returns_the_output(runner: Mock) -> None:
    result = TerminalToolbox().run_command({"command": "ipconfig"})

    assert result.content == "$ ipconfig\nIPv4 Address: 10.0.0.5"


def test_run_command_refuses_admin_rights_without_running_anything(runner: Mock) -> None:
    with pytest.raises(ToolError, match=ELEVATION_MESSAGE):
        TerminalToolbox().run_command({"command": "Start-Process cmd -Verb RunAs"})
    runner.assert_not_called()


def test_run_command_refuses_an_empty_command(runner: Mock) -> None:
    with pytest.raises(ToolError):
        TerminalToolbox().run_command({"command": "  "})


@pytest.mark.parametrize(
    ("command", "expected"),
    [("ipconfig /all", False), ("Remove-Item x", True), ("Start-Process cmd -Verb RunAs", False)],
)
def test_needs_approval_only_for_commands_that_could_change_something(command: str, expected: bool) -> None:
    assert needs_approval({"command": command}) is expected


def test_describe_command_shows_the_exact_command() -> None:
    assert (
        describe_command({"command": " Stop-Process -Name notepad "}) == "Run in PowerShell: Stop-Process -Name notepad"
    )


def test_describe_result_mentions_a_timeout_and_empty_output() -> None:
    text = describe_result("ping -t x", CommandResult(exit_code=-1, output="", timed_out=True))

    assert "Stopped after" in text and "printed nothing" in text


def test_describe_result_mentions_a_failing_exit_code() -> None:
    assert "(Exit code 1.)" in describe_result("x", CommandResult(exit_code=1, output="boom"))


def test_register_adds_a_tool_that_never_offers_always_allow() -> None:
    registry = ToolRegistry()

    TerminalToolbox().register(registry)

    tool = registry.get("run_command")
    assert tool is not None and tool.always_allowable is False
