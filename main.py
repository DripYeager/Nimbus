"""Entry point for Nimbus. Starts the application runtime and exits cleanly on shutdown."""

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


def main() -> None:
    """Builds and runs the app, propagating its Qt exit code to the process exit code. The
    packaged app is also its own Python for user-approved code runs (Nimbus.exe --run-code), and
    the bridge other AI apps start to search through Nimbus (Nimbus.exe --mcp)."""
    if len(sys.argv) > 2 and sys.argv[1] == RUN_CODE_FLAG:
        run_headless(_run_code)
        return
    if len(sys.argv) > 1 and sys.argv[1] == MCP_FLAG:
        from core.mcp_server import run_bridge

        run_headless(run_bridge)
        return
    # Imported here, so a code run doesn't load Qt and the whole app first.
    from core.app_runtime import AppRuntime

    sys.exit(AppRuntime().start())


def run_headless(job: Callable[[], None]) -> None:
    """Runs a mode nobody watches on screen. An error is printed to stderr and the process
    exits with code 1: left unhandled, the packaged (windowed) app would show an error dialog
    no one can see, and the process would hang until something killed it."""
    try:
        job()
    except SystemExit:
        raise
    except BaseException:
        # A windowed process may fail before its pipes are attached, with nowhere to print.
        if sys.stdout is not None:
            # What the job printed comes first, so the error stays the last thing in the output.
            sys.stdout.flush()
        if sys.stderr is not None:
            traceback.print_exc()
            sys.stderr.flush()
        sys.exit(FAILED_EXIT_CODE)


def _run_code() -> None:
    from core.code_sandbox import attach_std_streams, run_job

    attach_std_streams()
    run_job(Path(sys.argv[2]))


if __name__ == "__main__":
    main()
