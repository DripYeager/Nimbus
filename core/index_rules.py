"""
Decides which files Nimbus may look at: which folders are skipped entirely, which files are
cataloged by name, and which also get their contents read and embedded. Pure decisions from
settings — does not walk directories or read files.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from config.settings import Settings
from models.schema import FileCategory, IndexSource

CATEGORY_EXTENSIONS: dict[FileCategory, frozenset[str]] = {
    FileCategory.DOCUMENTS: frozenset({".docx", ".doc", ".odt", ".rtf", ".epub"}),
    FileCategory.PDFS: frozenset({".pdf"}),
    FileCategory.SPREADSHEETS: frozenset({".xlsx", ".xls", ".csv", ".ods"}),
    FileCategory.SLIDES: frozenset({".pptx", ".ppt", ".odp"}),
    FileCategory.TEXT: frozenset(
        {".txt", ".md", ".markdown", ".log", ".json", ".xml", ".yaml", ".yml", ".html", ".htm"}
    ),
    FileCategory.CODE: frozenset(
        {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".cs", ".cpp", ".c", ".h", ".go", ".rs", ".sql", ".sh", ".ps1"}
    ),
    FileCategory.EMAIL: frozenset({".msg", ".eml"}),
}

# Folders that are never useful to search and can hold hundreds of thousands of files.
DEFAULT_EXCLUDED_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        ".svn",
        "__pycache__",
        ".venv",
        "venv",
        ".idea",
        ".vscode",
        "$recycle.bin",
        "appdata",
        ".cache",
        "site-packages",
    }
)
# Temp files, partial downloads, and Office's "~$report.docx" lock files.
DEFAULT_EXCLUDED_FILES = (
    "~$*",
    "*.tmp",
    "*.crdownload",
    "*.part",
    "*.partial",
    "desktop.ini",
    "thumbs.db",
    ".ds_store",
)
BYTES_PER_MB = 1024 * 1024


@dataclass(frozen=True)
class IndexRules:
    """A snapshot of the user's indexing choices, cheap to consult once per file."""

    sources: tuple[IndexSource, ...]
    content_extensions: frozenset[str]
    max_file_bytes: int
    exclude_patterns: tuple[str, ...]

    @classmethod
    def from_settings(cls, settings: Settings) -> IndexRules:
        """Builds the rules from the current settings."""
        extensions = frozenset().union(*(CATEGORY_EXTENSIONS[c] for c in settings.file_categories))
        return cls(
            sources=tuple(settings.sources),
            content_extensions=extensions,
            max_file_bytes=settings.max_file_size_mb * BYTES_PER_MB,
            exclude_patterns=tuple(p.lower() for p in settings.exclude_patterns),
        )

    def is_excluded_dir(self, directory: Path) -> bool:
        """True for a folder whose whole subtree should be skipped."""
        name = directory.name.lower()
        return name in DEFAULT_EXCLUDED_DIRS or _matches_any(name, self.exclude_patterns)

    def is_excluded_file(self, path: Path) -> bool:
        """True for a file that shouldn't even be cataloged by name — either its own name is
        excluded, or one of the folders between its source root and itself is."""
        name = path.name.lower()
        if _matches_any(name, DEFAULT_EXCLUDED_FILES) or _matches_any(name, self.exclude_patterns):
            return True
        source = self.source_for(path)
        # Only folders below the source root count: a user who deliberately picks a folder
        # inside AppData still wants it indexed.
        root_depth = len(source.path.parts) if source else len(path.parts) - 1
        return any(self.is_excluded_dir(Path(part)) for part in path.parts[root_depth:-1])

    def should_read_contents(self, path: Path, size_bytes: int) -> bool:
        """True if this file's text should be extracted and embedded, not just its name."""
        source = self.source_for(path)
        if source is None or not source.include_contents:
            return False
        return path.suffix.lower() in self.content_extensions and 0 < size_bytes <= self.max_file_bytes

    def source_for(self, path: Path) -> IndexSource | None:
        """The most specific configured source folder containing path, if any."""
        matches = [s for s in self.sources if _is_within(path, s.path)]
        return max(matches, key=lambda s: len(s.path.parts), default=None)

    def is_covered(self, path: Path) -> bool:
        """True if path lives inside some configured source and isn't excluded."""
        return self.source_for(path) is not None and not self.is_excluded_file(path)


def _matches_any(name: str, patterns: tuple[str, ...] | frozenset[str]) -> bool:
    """Glob-matches an already-lowercased name against lowercased patterns."""
    return any(fnmatch(name, pattern) for pattern in patterns)


def _is_within(path: Path, root: Path) -> bool:
    """Case-insensitive containment check — Windows paths don't care about case."""
    try:
        Path(str(path).lower()).relative_to(str(root).lower())
    except ValueError:
        return False
    return True
