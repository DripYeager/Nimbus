"""
FastAPI dependency that hands each route the shared engine services. Owns lookup only, so
tests can swap in fakes through app.dependency_overrides.
"""

from __future__ import annotations

from fastapi import Request

from core.service_container import AppServices


def get_services(request: Request) -> AppServices:
    """The AppServices built at startup."""
    return request.app.state.services
