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


class QueryError(NimbusError):
    """A query couldn't be routed, retrieved, or answered."""


class ProviderError(NimbusError):
    """An LLM provider call failed, or the provider is unreachable."""


class AppLaunchError(NimbusError):
    """A discovered app wouldn't launch."""


class HotkeyError(NimbusError):
    """The configured hotkey string is invalid, or the OS refused to register it."""
