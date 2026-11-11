"""Entry point for Nimbus. Starts the application runtime and exits cleanly on shutdown."""

from __future__ import annotations

import sys


def main() -> None:
    """Runs a headless mode if asked (code sandbox, MCP bridge), hands over to a Nimbus that is
    already running, or starts the app; the app's exit code becomes the process's."""
    from core.launch_modes import run_headless_mode

    if run_headless_mode(sys.argv):
        return
    # A second launch (or File Explorer's "Ask Nimbus") only hands over to the running Nimbus,
    # so it checks before loading the engine's libraries, which takes seconds.
    from core.launch_args import ask_path_from
    from ui.single_instance import notify_running_instance

    if notify_running_instance(ask_path_from(sys.argv)):
        return
    from core.app_runtime import AppRuntime

    sys.exit(AppRuntime().start())


if __name__ == "__main__":
    main()
