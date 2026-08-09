"""Entry point for Nimbus. Starts the application runtime and exits cleanly on shutdown."""

from __future__ import annotations

from core.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    """Just proves the entry point boots — app_runtime takes over later."""
    logger.info("Nimbus starting up")


if __name__ == "__main__":
    main()
