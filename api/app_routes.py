"""
HTTP routes for installed apps: fuzzy lookup and launch. Routes only delegate to the app
catalog and launcher.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_services
from core.service_container import AppServices
from models.api import AppLaunchRequest, AppLaunchResult
from models.schema import AppEntry
from tools.action_toolbox import best_app_match
from tools.app_launcher import launch_app

router = APIRouter(prefix="/apps")

DEFAULT_APP_RESULTS = 10


@router.get("")
def find_apps(q: str = "", services: AppServices = Depends(get_services)) -> list[AppEntry]:
    """Best matches for q, or the first entries alphabetically when q is empty."""
    if not q.strip():
        return sorted(services.apps.entries(), key=lambda e: e.name.lower())[:DEFAULT_APP_RESULTS]
    return [entry for entry, _ in services.apps.find(q, limit=DEFAULT_APP_RESULTS)]


@router.post("/launch")
def launch(body: AppLaunchRequest, services: AppServices = Depends(get_services)) -> AppLaunchResult:
    entry = best_app_match(services.apps, body.name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No installed app looks like {body.name!r}.")
    launch_app(entry)
    return AppLaunchResult(launched=True, app=entry)
