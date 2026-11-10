"""
Translates settings written for Nimbus 1.x (.env files with LLM_PROVIDER=deepinfra,
WATCHED_DIRS, the old embedding defaults) into their current equivalents, so an upgrade never
fails to start over an old .env. Pure dict-in, dict-out; does not read files.
"""

from __future__ import annotations

import json
from typing import Any

DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/openai"
# 1.x's .env.example shipped these values. They were defaults, not choices, and 512-word chunks
# overflow the 2.x embedding model's 512-token window, so they're dropped in favour of the new
# defaults rather than carried forward.
V1_DEFAULTS = {"embedding_model": "all-MiniLM-L6-v2", "max_chunk_size": "512", "chunk_overlap": "50"}
LEGACY_KEYS = ("deepinfra_api_key", "deepinfra_model", "watched_dirs")


def migrate_legacy_values(data: dict[str, Any]) -> dict[str, Any]:
    """Returns data with every 1.x setting rewritten to its 2.x form and the old keys removed."""
    migrated = dict(data)
    if migrated.get("llm_provider") == "deepinfra":
        _migrate_deepinfra(migrated)
    if migrated.get("watched_dirs") and "sources" not in migrated:
        migrated["sources"] = [{"path": path} for path in _as_list(migrated["watched_dirs"])]
    for key, old_default in V1_DEFAULTS.items():
        if str(migrated.get(key)) == old_default:
            migrated.pop(key)
    for key in LEGACY_KEYS:
        migrated.pop(key, None)
    return migrated


def _migrate_deepinfra(data: dict[str, Any]) -> None:
    """DeepInfra became one instance of the generic OpenAI-compatible provider."""
    data["llm_provider"] = "openai_compatible"
    data.setdefault("compatible_base_url", DEEPINFRA_BASE_URL)
    if data.get("deepinfra_model"):
        data.setdefault("compatible_model", data["deepinfra_model"])
    if data.get("deepinfra_api_key"):
        data.setdefault("compatible_api_key", data["deepinfra_api_key"])


def _as_list(value: Any) -> list[str]:
    """WATCHED_DIRS arrives as a JSON string from .env, or as a list from code."""
    if isinstance(value, str):
        return json.loads(value)
    return list(value)
