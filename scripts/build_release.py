"""
Builds the Windows release: renders the icon files, runs PyInstaller with packaging/nimbus.spec,
and zips the output folder into dist/Nimbus-<version>-win64.zip. Does not sign or upload.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from core.logger import get_logger  # noqa: E402
from ui.theme.icons import export_icon_files  # noqa: E402

logger = get_logger(__name__)


def project_version() -> str:
    """The version declared in pyproject.toml."""
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def render_icons() -> None:
    """The icon is code-drawn, so it's rendered fresh for every build."""
    app = QApplication.instance() or QApplication([])
    export_icon_files(ROOT / "assets")
    app.quit()


def run_pyinstaller() -> Path:
    """Builds dist/Nimbus/ and returns its path."""
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(ROOT / "packaging" / "nimbus.spec")]
    subprocess.run(command, cwd=ROOT, check=True)
    return ROOT / "dist" / "Nimbus"


def main() -> None:
    render_icons()
    output = run_pyinstaller()
    archive = shutil.make_archive(str(ROOT / "dist" / f"Nimbus-{project_version()}-win64"), "zip", output)
    logger.info("Release built", extra={"folder": str(output), "archive": archive})


if __name__ == "__main__":
    main()
