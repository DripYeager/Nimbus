"""The FastAPI app. Bound to 127.0.0.1 — nothing in here is reachable from the network."""

from __future__ import annotations

from api.server import app

__all__ = ["app"]
