"""Entry point for Nimbus. Starts the application runtime and exits cleanly on shutdown."""

from __future__ import annotations

import sys

from core.app_runtime import AppRuntime


def main() -> None:
    """Builds and runs the app, propagating its Qt exit code to the process exit code."""
    sys.exit(AppRuntime().start())


if __name__ == "__main__":
    main()
