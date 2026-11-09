"""Engine internals: logging, errors, indexing, retrieval and the assistant loop.

Only the lightweight foundations are re-exported here. The indexing and query modules pull in
parsers, ONNX runtimes and LLM SDKs, so callers import those from their own modules directly
instead of paying for all of them whenever they just need an exception class.
"""

from __future__ import annotations

from core.exceptions import (
    AppLaunchError,
    ConversationNotFoundError,
    HotkeyError,
    IndexingError,
    NimbusError,
    ParsingError,
    ProviderError,
    QueryError,
    SecretStoreError,
    SettingsError,
    ToolError,
    ToolsUnsupportedError,
    UnsupportedFileTypeError,
    UsageCapReachedError,
)
from core.logger import get_logger

__all__ = [
    "NimbusError",
    "IndexingError",
    "ParsingError",
    "UnsupportedFileTypeError",
    "QueryError",
    "ProviderError",
    "ToolsUnsupportedError",
    "UsageCapReachedError",
    "AppLaunchError",
    "ToolError",
    "HotkeyError",
    "SettingsError",
    "SecretStoreError",
    "ConversationNotFoundError",
    "get_logger",
]
