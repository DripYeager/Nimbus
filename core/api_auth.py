"""
Who may talk to Nimbus's local API. Binding to 127.0.0.1 keeps other computers out, but not
other programs on this PC, or a web page that tricks the browser into calling localhost. So
every request must carry a secret that only this process knows (it's made at startup and never
written to disk; the chat window and the engine share it in memory), and must be addressed to
127.0.0.1 or localhost by name, which defeats DNS-rebinding pages. Owns the secret and the
checks; enforcing them on each request is the API layer's job.
"""

from __future__ import annotations

import hmac
import os
import secrets
import threading

TOKEN_HEADER = "X-Nimbus-Token"
# Lets someone run the engine on its own (uvicorn api.server:app) and still call it.
TOKEN_ENV_VAR = "NIMBUS_API_TOKEN"
TOKEN_BYTES = 32
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost"})

_token: str | None = None
_lock = threading.Lock()


def session_token() -> str:
    """This run's secret: from NIMBUS_API_TOKEN if set, otherwise random, made once."""
    global _token
    with _lock:
        if _token is None:
            _token = os.environ.get(TOKEN_ENV_VAR) or secrets.token_urlsafe(TOKEN_BYTES)
        return _token


def auth_headers() -> dict[str, str]:
    """The header every API call from the desktop UI sends."""
    return {TOKEN_HEADER: session_token()}


def is_valid_token(presented: str | None) -> bool:
    """Constant-time comparison, so the secret can't be guessed from response timings."""
    return presented is not None and hmac.compare_digest(presented, session_token())


def is_allowed_host(host_header: str | None) -> bool:
    """True when the request was addressed to this machine by name ("127.0.0.1:8765")."""
    if not host_header:
        return False
    host = host_header.rsplit(":", 1)[0] if not host_header.startswith("[") else host_header
    return host.lower() in ALLOWED_HOSTS
