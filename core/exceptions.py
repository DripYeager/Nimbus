"""
Defines the domain exception hierarchy used across Nimbus.
Does not catch or log exceptions — callers catch these and decide how to respond.
"""

from __future__ import annotations


class NimbusError(Exception):
    """Base class for every domain error Nimbus raises."""


class IndexingError(NimbusError):
    """A file failed somewhere in the parse/chunk/embed/store pipeline."""


class ParsingError(NimbusError):
    """A document couldn't be converted to text."""


class UnsupportedFileTypeError(ParsingError):
    """No converter exists for this file's type — expected for some files, not a real failure."""


class QueryError(NimbusError):
    """A query couldn't be routed, retrieved, or answered."""


class ProviderError(NimbusError):
    """An LLM provider call failed, or the provider is unreachable."""


class ToolsUnsupportedError(ProviderError):
    """The selected model can't do tool calling, so the agent has to fall back to plain RAG."""


class UsageCapReachedError(ProviderError):
    """The user's daily model-call cap is used up."""


class AppLaunchError(NimbusError):
    """A discovered app wouldn't launch."""


class ToolError(NimbusError):
    """A tool was called with bad arguments or couldn't finish its job."""


class HotkeyError(NimbusError):
    """The configured hotkey string is invalid, or the OS refused to register it."""


class SettingsError(NimbusError):
    """Saved settings couldn't be read, or a requested change isn't valid."""


class SecretStoreError(NimbusError):
    """The OS credential store refused to save or read an API key."""


class ConversationNotFoundError(NimbusError):
    """A chat ID doesn't exist (any more)."""


class AutostartError(NimbusError):
    """The Startup-folder shortcut couldn't be created or removed."""
