"""
The PC diagnostics tools. top_processes reports what's using the CPU and memory right now.
run_command lets the assistant run a PowerShell command to answer other questions about this
PC ("why is my Wi-Fi slow?"): read-only information commands run straight away; anything else
waits for the user's approval on a card showing the exact command, every time (there's no
"always allow" for commands); asking for administrator rights is refused without a card. Owns
the tools' wording and results; policy, execution and sampling live in core.
"""

from __future__ import annotations

from typing import Any

from core.command_policy import ELEVATION_MESSAGE, asks_for_elevation, is_read_only
from core.command_runner import DEFAULT_TIMEOUT_S, CommandResult, run_powershell
from core.exceptions import ToolError
from core.process_monitor import busiest_programs, describe_usage
from models.chat import ToolResult
from tools.registry import Tool, ToolRegistry, object_schema, string_param, tool_spec

RUN_COMMAND = tool_spec(
    "run_command",
    "Run a Windows PowerShell command on this PC and read what it prints, to answer questions about the "
    "computer: network (ipconfig, ping, Get-NetAdapter, netsh wlan show interfaces), disks (Get-Volume), "
    "system (systeminfo), installed apps (winget list). For what's using CPU or memory, use top_processes "
    "instead. Read-only commands run at once; anything that changes something waits for the user's "
    "approval. No administrator rights.",
    object_schema({"command": string_param("The PowerShell command line to run")}, ["command"]),
)
TOP_PROCESSES = tool_spec(
    "top_processes",
    "What's using this PC right now: the busiest programs by CPU (live, measured over one second) and "
    "by memory, plus the whole machine's CPU and memory use. Use this for 'why is my PC slow', "
    "'what's eating my CPU/RAM'.",
    object_schema({}),
)
NO_OUTPUT = "(The command printed nothing.)"


class TerminalToolbox:
    """Registers run_command and top_processes."""

    def register(self, registry: ToolRegistry) -> None:
        registry.register(Tool(TOP_PROCESSES, self.top_processes, lambda _: "Checked what's using the PC"))
        registry.register(
            Tool(
                RUN_COMMAND,
                self.run_command,
                describe_command,
                confirm_when=needs_approval,
                always_allowable=False,
            )
        )

    def top_processes(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(content=describe_usage(busiest_programs()))

    def run_command(self, args: dict[str, Any]) -> ToolResult:
        command = str(args.get("command", "")).strip()
        if not command:
            raise ToolError("No command was given.")
        if asks_for_elevation(command):
            raise ToolError(ELEVATION_MESSAGE)
        return ToolResult(content=describe_result(command, run_powershell(command)))


def needs_approval(args: dict[str, Any], user_text: str = "") -> bool:
    """Read-only commands, and ones that will be refused anyway, don't need a card."""
    command = str(args.get("command", ""))
    return not (is_read_only(command) or asks_for_elevation(command))


def describe_command(args: dict[str, Any]) -> str:
    """The chip and approval-card text: the exact command, nothing paraphrased."""
    return f"Run in PowerShell: {str(args.get('command', '')).strip()}"


def describe_result(command: str, result: CommandResult) -> str:
    """What the model reads back: the output, plus how it ended when that matters."""
    lines = [f"$ {command}"]
    if result.timed_out:
        lines.append(f"(Stopped after {DEFAULT_TIMEOUT_S:.0f} seconds; this is what it printed until then.)")
    elif result.exit_code != 0:
        lines.append(f"(Exit code {result.exit_code}.)")
    lines.append(result.output or NO_OUTPUT)
    return "\n".join(lines)
