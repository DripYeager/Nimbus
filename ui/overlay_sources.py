"""
Renders the overlay's source citations as clickable, muted links and opens the clicked file in
its OS-registered default app. Owns source-citation rendering and file-opening only — the
window that hosts this widget owns everything else about what the user sees.
"""

from __future__ import annotations

import html
import os
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QWidget

from core.logger import get_logger
from models.schema import SourceRef
from ui.overlay_theme import TEXT_MUTED

logger = get_logger(__name__)


class SourceCitations(QLabel):
    """A muted citation row where each source name is a link that opens its file."""

    open_failed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sources: list[SourceRef] = []
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        self.linkActivated.connect(self._open_source)

    def set_sources(self, sources: list[SourceRef]) -> None:
        """Renders each source as a clickable citation link, replacing whatever was shown before."""
        self._sources = sources
        links = (_source_link(i, source) for i, source in enumerate(sources))
        self.setText(" · ".join(links))

    def clear(self) -> None:
        """Clears the citation text and drops the source list backing it."""
        self._sources = []
        super().clear()

    def _open_source(self, href: str) -> None:
        """Opens the clicked source's file in its OS-registered default app."""
        source = self._sources[int(href)]
        try:
            os.startfile(Path(source.file_path))
        except OSError as e:
            logger.warning("Couldn't open source file", extra={"path": source.file_path, "error": str(e)})
            self.open_failed.emit(f"Couldn't open {source.file_name}: {e}")


def _source_link(index: int, source: SourceRef) -> str:
    """Builds one citation's anchor tag, styled to match the muted token, not Qt's default blue."""
    name = html.escape(source.file_name)
    return f'<a href="{index}" style="color: {TEXT_MUTED}; text-decoration: underline;">{name}</a>'
