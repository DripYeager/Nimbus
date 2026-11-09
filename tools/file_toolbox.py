"""
The read-only file tools the assistant can call: search by meaning, find by name, list recent
files, read, summarize, and inspect a file. Every path is checked against the user's chosen
folders before it's touched, so the model can never read outside what was shared. Owns the
tool definitions and their result formatting; the lookups themselves live in file_tools,
summary_tools and the file catalog.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.exceptions import ToolError
from core.file_catalog import FileCatalog
from core.retriever import Retriever
from llm.provider import LLMProvider
from models.chat import ToolResult
from models.schema import CatalogMatch
from tools.file_tools import get_metadata, rank_unique_files, source_ref_for, source_ref_for_match
from tools.registry import (
    Tool,
    ToolRegistry,
    file_name_arg,
    integer_param,
    object_schema,
    string_param,
    tool_spec,
)
from tools.summary_tools import read_document_excerpt, summarize_document

DEFAULT_READ_WORDS = 1500
MAX_READ_WORDS = 6000
EXCERPT_CHARS = 280
MAX_RESULTS = 20
MAX_RECENT_DAYS = 3650

_PATH_ONLY = object_schema({"path": string_param("Full path, or exact file name")}, ["path"])
SEARCH_FILES = tool_spec(
    "search_files",
    "Search the user's files by topic or meaning. Returns files with excerpts.",
    object_schema({"query": string_param("What to look for"), "limit": integer_param("Max files")}, ["query"]),
)
FIND_BY_NAME = tool_spec(
    "find_files_by_name",
    "Find files by (part of) their name, any file type — including photos, installers and archives.",
    object_schema({"name": string_param("File name or part of it"), "limit": integer_param("Max files")}, ["name"]),
)
LIST_RECENT = tool_spec(
    "list_recent_files",
    "List files changed in the last N days, e.g. today's downloads.",
    object_schema(
        {"days": integer_param("1 = today"), "folder": string_param("e.g. Downloads"), "limit": integer_param("Max")}
    ),
)
READ_FILE = tool_spec(
    "read_file",
    "Read the text of one file.",
    object_schema(
        {"path": string_param("Full path, or exact file name"), "max_words": integer_param("Default 1500")}, ["path"]
    ),
)
SUMMARIZE_FILE = tool_spec("summarize_file", "Summarize a whole document, however long.", _PATH_ONLY)
FILE_INFO = tool_spec("get_file_info", "Size, created/modified dates and folder of one file.", _PATH_ONLY)


class FileToolbox:
    """Builds and serves the file tools. path_guard is asked on every call, so a folder the
    user removes in Settings stops being readable immediately."""

    def __init__(
        self, retriever: Retriever, catalog: FileCatalog, path_guard: Callable[[Path], bool], provider: LLMProvider
    ) -> None:
        self._retriever = retriever
        self._catalog = catalog
        self._path_guard = path_guard
        self._provider = provider

    def register(self, registry: ToolRegistry) -> None:
        """Adds every file tool to registry."""
        for tool in self._tools():
            registry.register(tool)

    def search_files(self, args: dict[str, Any]) -> ToolResult:
        """Finds files whose contents match a topic, with the best excerpt from each."""
        limit = _clamp(args.get("limit", 5))
        chunks = self._retriever.retrieve(args["query"], top_k=limit * 4)
        files = rank_unique_files(chunks)[:limit]
        if not files:
            return ToolResult(content="No indexed file matched that. Try find_files_by_name or other words.")
        excerpts = {c.file_path: c.chunk_text for c in reversed(chunks)}
        lines = [
            f"{i}. {f.file_name} — {f.file_path}\n   {_excerpt(excerpts[f.file_path])}" for i, f in enumerate(files, 1)
        ]
        return ToolResult(content="\n".join(lines), sources=files)

    def find_files_by_name(self, args: dict[str, Any]) -> ToolResult:
        """Finds files whose names resemble the given name, including files that aren't text."""
        matches = self._catalog.search_names(args["name"], limit=_clamp(args.get("limit", 8)))
        if not matches:
            return ToolResult(content=f"No file name looks like {args['name']!r}.")
        return _matches_result(matches)

    def list_recent_files(self, args: dict[str, Any]) -> ToolResult:
        """Lists files modified in the last N days, optionally only inside one folder."""
        days = max(1, min(int(args.get("days", 1)), MAX_RECENT_DAYS))
        since = datetime.combine(datetime.now().date() - timedelta(days=days - 1), datetime.min.time())
        matches = self._catalog.recent_files(since, limit=MAX_RESULTS * 5)
        folder = str(args.get("folder", "")).lower()
        if folder:
            matches = [m for m in matches if folder in str(Path(m.file_path).parent).lower()]
        matches = matches[: _clamp(args.get("limit", 15))]
        if not matches:
            return ToolResult(content="No files changed in that period.")
        return _matches_result(matches)

    def read_file(self, args: dict[str, Any]) -> ToolResult:
        """Returns a file's text, cut to a word budget."""
        path = self._resolve(args["path"])
        max_words = max(1, min(int(args.get("max_words", DEFAULT_READ_WORDS)), MAX_READ_WORDS))
        text, truncated = read_document_excerpt(path, max_words)
        suffix = "\n\n[truncated — use summarize_file for the whole document]" if truncated else ""
        body = text or "(no text could be extracted)"
        return ToolResult(content=f"{path.name}:\n{body}{suffix}", sources=[source_ref_for(path)])

    def summarize_file(self, args: dict[str, Any]) -> ToolResult:
        """Summarizes a whole document of any length."""
        path = self._resolve(args["path"])
        return ToolResult(content=summarize_document(path, self._provider), sources=[source_ref_for(path)])

    def get_file_info(self, args: dict[str, Any]) -> ToolResult:
        """Size, created and modified time, and location of one file."""
        path = self._resolve(args["path"])
        meta = get_metadata(path)
        if meta is None:
            return ToolResult(content=f"{path} no longer exists.", is_error=True)
        content = (
            f"{meta.file_name}\nFolder: {path.parent}\nSize: {_size(meta.size_bytes)}\n"
            f"Created: {meta.created_at:%Y-%m-%d %H:%M}\nModified: {meta.modified_at:%Y-%m-%d %H:%M}"
        )
        return ToolResult(content=content, sources=[source_ref_for(path)])

    def _resolve(self, raw: str) -> Path:
        """Turns the model's path (full, or just a file name) into an allowed, existing file."""
        path = Path(raw).expanduser()
        if not path.is_absolute():
            matches = self._catalog.search_names(raw, limit=1)
            if not matches:
                raise ToolError(f"Couldn't find a file called {raw!r}. Use find_files_by_name first.")
            path = Path(matches[0].file_path)
        # Resolving first means "Documents\..\..\secret.txt" can't slip past the folder check.
        path = path.resolve()
        if not self._path_guard(path):
            raise ToolError(f"{path} is outside the folders the user shared with Nimbus.")
        if not path.is_file():
            raise ToolError(f"{path} doesn't exist (any more).")
        return path

    def _tools(self) -> list[Tool]:
        """Pairs each spec with its handler and its plain-language description."""
        return [
            Tool(SEARCH_FILES, self.search_files, lambda a: f"Searched files for “{a.get('query', '')}”"),
            Tool(FIND_BY_NAME, self.find_files_by_name, lambda a: f"Looked for files named “{a.get('name', '')}”"),
            Tool(LIST_RECENT, self.list_recent_files, lambda a: "Listed recent files"),
            Tool(READ_FILE, self.read_file, lambda a: f"Read {file_name_arg(a)}"),
            Tool(SUMMARIZE_FILE, self.summarize_file, lambda a: f"Summarized {file_name_arg(a)}"),
            Tool(FILE_INFO, self.get_file_info, lambda a: f"Checked {file_name_arg(a)}"),
        ]


def _matches_result(matches: list[CatalogMatch]) -> ToolResult:
    """Formats catalog matches as a numbered list plus clickable sources."""
    lines = [
        f"{i}. {m.file_name} — {m.file_path} ({_size(m.size_bytes)}, modified {m.modified_at:%Y-%m-%d %H:%M})"
        for i, m in enumerate(matches, 1)
    ]
    sources = [source_ref_for_match(m) for m in matches]
    return ToolResult(content="\n".join(lines), sources=sources)


def _excerpt(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= EXCERPT_CHARS else flat[:EXCERPT_CHARS] + "…"


def _size(size_bytes: float) -> str:
    """Human-readable size, e.g. 2.4 MB."""
    for unit in ("B", "KB", "MB"):
        if size_bytes < 1024:
            return f"{size_bytes:.0f} {unit}" if unit == "B" else f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} GB"


def _clamp(value: Any) -> int:
    """Keeps a model-supplied limit between 1 and MAX_RESULTS."""
    return max(1, min(int(value), MAX_RESULTS))
