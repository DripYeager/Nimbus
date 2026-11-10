"""
Answers the most common direct commands — "open spotify", "find resume.pdf" — instantly and
without any model call, when the match is unambiguous. Anything less certain returns None and
goes to the full assistant. Owns pattern matching and confidence thresholds only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from core.exceptions import NimbusError
from core.file_catalog import FileCatalog
from core.logger import get_logger
from models.schema import CatalogMatch, SourceRef
from tools.action_toolbox import ActionToolbox
from tools.app_launcher import launch_app
from tools.file_tools import source_ref_for_match
from tools.system_tools import open_path

logger = get_logger(__name__)

OPEN_PATTERN = re.compile(r"^\s*(?:please\s+)?(?:open|launch|start|run)\s+(?:the\s+|my\s+)?(.+?)\s*[.!]?\s*$", re.I)
FIND_PATTERN = re.compile(
    r"^\s*(?:find|locate|where(?:'s| is| are))\s+(?:the\s+|my\s+)?(?:file\s+)?(.+?)\s*\??\s*$", re.I
)
FILE_NAME_PATTERN = re.compile(r"\.[a-z0-9]{2,5}$", re.I)
# High bars on purpose: a wrong instant answer is worse than a two-second assistant answer.
CONFIDENT_FILE_SCORE = 90.0
CONFIDENT_APP_SCORE = 90.0
MAX_FIND_RESULTS = 5
SHARED_OVERFETCH = 3


@dataclass
class FastAnswer:
    text: str
    sources: list[SourceRef] = field(default_factory=list)


class FastPath:
    """Tries to answer a message without the model."""

    def __init__(self, catalog: FileCatalog, actions: ActionToolbox) -> None:
        self._catalog = catalog
        self._actions = actions

    def try_answer(self, text: str) -> FastAnswer | None:
        """A complete answer for an unambiguous open/find command, else None."""
        if " and " in text.lower():
            return None
        open_match = OPEN_PATTERN.match(text)
        if open_match:
            return self._open(open_match.group(1))
        find_match = FIND_PATTERN.match(text)
        if find_match and FILE_NAME_PATTERN.search(find_match.group(1)):
            return self._find(find_match.group(1))
        return None

    def _open(self, target: str) -> FastAnswer | None:
        """Opens a named file if target looks like one, otherwise an installed app."""
        if FILE_NAME_PATTERN.search(target):
            return self._open_file(target)
        entry = self._actions.best_app_match(target, min_score=CONFIDENT_APP_SCORE)
        if entry is None:
            return None
        try:
            launch_app(entry)
        except NimbusError as e:
            return FastAnswer(text=f"I found **{entry.name}** but couldn't start it: {e}")
        return FastAnswer(text=f"Opening **{entry.name}**.")

    def _open_file(self, name: str) -> FastAnswer | None:
        """Opens the single file that clearly matches name."""
        best = self._confident_file(name)
        if best is None:
            return None
        try:
            open_path(Path(best.file_path))
        except NimbusError as e:
            return FastAnswer(
                text=f"I found **{best.file_name}** but couldn't open it: {e}", sources=[source_ref_for_match(best)]
            )
        return FastAnswer(text=f"Opening **{best.file_name}**.", sources=[source_ref_for_match(best)])

    def _find(self, name: str) -> FastAnswer | None:
        """Lists the files matching name, when at least one is a confident match."""
        matches = self._shared_matches(name, MAX_FIND_RESULTS)
        if not matches or matches[0].score < CONFIDENT_FILE_SCORE:
            return None
        lines = [f"- **{m.file_name}** — `{Path(m.file_path).parent}`" for m in matches]
        return FastAnswer(
            text="Here's what I found:\n\n" + "\n".join(lines), sources=[source_ref_for_match(m) for m in matches]
        )

    def _confident_file(self, name: str) -> CatalogMatch | None:
        matches = self._shared_matches(name, 1)
        return matches[0] if matches and matches[0].score >= CONFIDENT_FILE_SCORE else None

    def _shared_matches(self, name: str, limit: int) -> list[CatalogMatch]:
        """The catalog's best name matches, minus files from folders that are no longer shared —
        the catalog can still list a file from a folder the user just un-shared."""
        # Over-fetch so unshared hits don't use up slots that shared files should fill.
        matches = self._catalog.search_names(name, limit=limit * SHARED_OVERFETCH)
        return [m for m in matches if self._actions.is_shared(Path(m.file_path))][:limit]
