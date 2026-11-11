"""
Runs one PowerShell command line for the assistant and returns what it printed. Hidden window,
no profile, no input, UTF-8 output, the user's normal rights (never elevated), and a time limit
that kills the whole process tree, so "ping -t" can't run forever. Long output keeps its start
and its end. Owns execution only; whether a command may run without asking is command_policy's.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import psutil

from core.exceptions import ToolError
from core.logger import get_logger

logger = get_logger(__name__)

POWERSHELL = (
    Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
)
DEFAULT_TIMEOUT_S = 30.0
MAX_OUTPUT_CHARS = 8000
KEEP_TAIL_CHARS = 2000
# Output encoding first, so native tools' text (ipconfig, ping) comes back as UTF-8; the command
# runs inside a script block and Out-String keeps PowerShell from cutting wide tables at 80 columns.
_WRAPPER = (
    "$ProgressPreference = 'SilentlyContinue'; [Console]::OutputEncoding = [Text.Encoding]::UTF8; "
    "& {{ {command} }} | Out-String -Width 250"
)


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    output: str
    timed_out: bool = False


def run_powershell(command: str, timeout_s: float = DEFAULT_TIMEOUT_S, cwd: Path | None = None) -> CommandResult:
    """Runs command and returns its exit code and combined, trimmed output.

    Raises:
        ToolError: PowerShell couldn't be started.
    """
    arguments = [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", _WRAPPER.format(command=command)]
    try:
        process = subprocess.Popen(
            arguments,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(cwd or Path.home()),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as e:
        raise ToolError(f"Couldn't start PowerShell: {e}") from e
    try:
        raw, _ = process.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill_tree(process.pid)
        raw, _ = process.communicate()
        logger.info("Command timed out", extra={"seconds": timeout_s})
        return CommandResult(exit_code=-1, output=trim_output(_decode(raw)), timed_out=True)
    return CommandResult(exit_code=process.returncode, output=trim_output(_decode(raw)))


def trim_output(text: str, limit: int = MAX_OUTPUT_CHARS, tail: int = KEEP_TAIL_CHARS) -> str:
    """text without trailing blank lines, cut in the middle when it's longer than limit."""
    text = "\n".join(line.rstrip() for line in text.strip().splitlines())
    if len(text) <= limit:
        return text
    head = text[: limit - tail]
    cut = len(text) - limit
    return f"{head}\n\n[... {cut:,} characters cut ...]\n\n{text[-tail:]}"


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").replace("\r\n", "\n")


def _kill_tree(pid: int) -> None:
    """Ends the command and everything it started (ping, a child script...)."""
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except psutil.Error:
        pass
