"""
Opens a source file from an answer, and a PDF at the page the answer cites. Windows drops a
"#page=12" when it opens a file, so for PDFs this asks Windows which app opens them and gives
that app its own "go to page" argument (browsers, Acrobat and SumatraPDF each have one). Any
other app, or any failure, falls back to opening the file normally. Owns launching only.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices

from core.logger import get_logger

logger = get_logger(__name__)

PDF_EXTENSION = ".pdf"
# AssocQueryStringW: ASSOCF_NONE, ASSOCSTR_EXECUTABLE, and a buffer long enough for any path.
ASSOCF_NONE = 0
ASSOCSTR_EXECUTABLE = 2
PATH_BUFFER_CHARS = 1024
S_OK = 0
BROWSERS = frozenset({"msedge.exe", "chrome.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe"})
ACROBAT = frozenset({"acrord32.exe", "acrobat.exe"})
SUMATRA = frozenset({"sumatrapdf.exe"})


def open_source(path: str, page: int | None = None) -> None:
    """Opens path, at page when it's a PDF and the user's PDF app can jump to a page."""
    if page is not None and Path(path).suffix.lower() == PDF_EXTENSION:
        command = page_command(default_app_for(PDF_EXTENSION), path, page)
        if command is not None and _launch(command):
            return
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def page_command(app: str | None, path: str, page: int) -> list[str] | None:
    """The command line that opens path at page in app, or None if app has no such option."""
    if app is None:
        return None
    name = Path(app).name.lower()
    if name in BROWSERS:
        return [app, f"{QUrl.fromLocalFile(path).toString()}#page={page}"]
    if name in ACROBAT:
        return [app, "/A", f"page={page}", path]
    if name in SUMATRA:
        return [app, "-page", str(page), path]
    return None


def default_app_for(extension: str) -> str | None:
    """The program Windows opens files of this extension with, or None if it can't tell."""
    if sys.platform != "win32":
        return None
    buffer = ctypes.create_unicode_buffer(PATH_BUFFER_CHARS)
    size = wintypes.DWORD(PATH_BUFFER_CHARS)
    result = ctypes.windll.shlwapi.AssocQueryStringW(
        ASSOCF_NONE, ASSOCSTR_EXECUTABLE, extension, None, buffer, ctypes.byref(size)
    )
    return buffer.value if result == S_OK and buffer.value else None


def _launch(command: list[str]) -> bool:
    try:
        subprocess.Popen(command, close_fds=True)
    except OSError as e:
        logger.warning("Couldn't open the PDF at its page", extra={"app": command[0], "error": str(e)})
        return False
    return True
