"""
The modes the packaged app runs in besides the desktop app itself: the sandbox for an approved
Python run (Nimbus.exe --run-code job.json) and the MCP bridge other AI apps start (Nimbus.exe
--mcp). Both run headless, so an error has to end the process instead of opening a dialog no
one can see. Owns choosing and running those modes; the work itself lives in
core/code_sandbox.py and core/mcp_server.py.
"""

from __future__ import annotations

import sys
import traceback
from collections.abc import Callable
from pathlib import Path

# Kept in step with core/code_sandbox.py and core/mcp_server.py, without importing them for
# every normal start.
RUN_CODE_FLAG = "--run-code"
MCP_FLAG = "--mcp"
FAILED_EXIT_CODE = 1


def run_headless_mode(argv: list[str]) -> bool:
    """Runs the code sandbox or the MCP bridge if argv asks for one; False for a normal start."""
    if len(argv) > 2 and argv[1] == RUN_CODE_FLAG:
        run_headless(lambda: _run_code(Path(argv[2])))
        return True
    if len(argv) > 1 and argv[1] == MCP_FLAG:
        from core.mcp_server import run_bridge

        run_headless(run_bridge)
        return True
    return False


def run_headless(job: Callable[[], None]) -> None:
    """Runs a mode nobody watches on screen. An error is printed to stderr and the process
    exits with code 1: left unhandled, the packaged (windowed) app would show an error dialog
    no one can see, and the process would hang until something killed it."""
    try:
        job()
    except SystemExit:
        raise
    except BaseException:
        if sys.stdout is not None:
            # What the job printed comes first, so the error stays the last thing in the output.
            sys.stdout.flush()
        # A windowed process may fail before its pipes are attached, with nowhere to print.
        if sys.stderr is not None:
            traceback.print_exc()
            sys.stderr.flush()
        sys.exit(FAILED_EXIT_CODE)


def _run_code(job_file: Path) -> None:
    from core.code_sandbox import attach_std_streams, run_job

    attach_std_streams()
    run_job(job_file)
