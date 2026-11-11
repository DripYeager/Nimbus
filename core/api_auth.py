"""
Who may talk to Nimbus's local API. Binding to 127.0.0.1 keeps other computers out, but not
other programs on this PC, or a web page that tricks the browser into calling localhost. So
every request must carry a secret that only this process knows (it's made at startup and never
written to disk; the chat window and the engine share it in memory), and must be addressed to
127.0.0.1 or localhost by name, which defeats DNS-rebinding pages. A second secret, the bridge
token, only opens the read-only /tools routes; it's written to a file in the user's own data
folder only while "Share with other AI apps" is on, so the MCP bridge (core/mcp_server.py) can
read it. Owns the secrets and the checks; enforcing them on each request is the API layer's job.
"""

from __future__ import annotations

import hmac
import os
import secrets
import threading
from pathlib import Path

TOKEN_HEADER = "X-Nimbus-Token"
# Lets someone run the engine on its own (uvicorn api.server:app) and still call it.
TOKEN_ENV_VAR = "NIMBUS_API_TOKEN"
TOKEN_BYTES = 32
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost"})
BRIDGE_PATH_PREFIX = "/tools/"
BRIDGE_TOKEN_FILE = "mcp_bridge_token"

_token: str | None = None
_bridge_token = secrets.token_urlsafe(TOKEN_BYTES)
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


def is_valid_bridge_token(presented: str | None) -> bool:
    """The MCP bridge's secret; it opens nothing but the /tools routes."""
    return presented is not None and hmac.compare_digest(presented, _bridge_token)


def write_bridge_token(path: Path) -> None:
    """Writes this run's bridge secret for the MCP bridge to read. The data folder is inside
    the user's profile, which other Windows accounts can't read."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_bridge_token, encoding="utf-8")


def remove_bridge_token(path: Path) -> None:
    path.unlink(missing_ok=True)


def read_bridge_token(path: Path) -> str | None:
    """The running engine's bridge secret, or None when sharing is off or Nimbus isn't running."""
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def is_allowed_host(host_header: str | None) -> bool:
    """True when the request was addressed to this machine by name ("127.0.0.1:8765")."""
    if not host_header:
        return False
    host = host_header.rsplit(":", 1)[0] if not host_header.startswith("[") else host_header
    return host.lower() in ALLOWED_HOSTS
