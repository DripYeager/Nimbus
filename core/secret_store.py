"""
Stores and reads provider API keys in the operating system's credential store (Windows
Credential Manager), so a key never sits in a plain-text file. Falls back to a key from
.env for developers. Does not decide which provider is active.
"""

from __future__ import annotations

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from config.settings import Settings
from core.exceptions import SecretStoreError
from core.logger import get_logger
from models.chat import ProviderName

logger = get_logger(__name__)

SERVICE_NAME = "Nimbus"
# The Settings field holding each provider's .env developer fallback.
ENV_KEY_FIELDS = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "openai_compatible": "compatible_api_key",
}
KEYED_PROVIDERS: frozenset[str] = frozenset(ENV_KEY_FIELDS)


def save_api_key(provider: ProviderName, api_key: str) -> None:
    """Saves (or replaces) the key for provider in the OS credential store."""
    _require_keyed(provider)
    if not api_key.strip():
        raise SecretStoreError("The API key is empty. Paste the full key and try again.")
    try:
        keyring.set_password(SERVICE_NAME, provider, api_key.strip())
    except KeyringError as e:
        raise SecretStoreError(f"Windows refused to save the {provider} key: {e}") from e
    logger.info("Saved API key to the credential store", extra={"provider": provider})


def delete_api_key(provider: ProviderName) -> None:
    """Removes provider's stored key; a no-op if there wasn't one."""
    _require_keyed(provider)
    try:
        keyring.delete_password(SERVICE_NAME, provider)
    except PasswordDeleteError:
        return
    except KeyringError as e:
        raise SecretStoreError(f"Couldn't remove the {provider} key: {e}") from e


def get_api_key(provider: ProviderName, settings: Settings) -> str | None:
    """The stored key for provider, else the .env developer fallback, else None."""
    if provider not in KEYED_PROVIDERS:
        return None
    try:
        stored = keyring.get_password(SERVICE_NAME, provider)
    except KeyringError as e:
        logger.warning("Couldn't read the credential store", extra={"provider": provider, "error": str(e)})
        stored = None
    return stored or getattr(settings, ENV_KEY_FIELDS[provider], None)


def has_api_key(provider: ProviderName, settings: Settings) -> bool:
    """True if a key is available for provider from either source."""
    return bool(get_api_key(provider, settings))


def _require_keyed(provider: str) -> None:
    """Ollama runs locally and has no key, so asking to store one is always a caller bug."""
    if provider not in KEYED_PROVIDERS:
        raise SecretStoreError(f"{provider} doesn't use an API key.")
