"""
HTTP routes for indexing: progress, per-folder counts, pause/resume and rebuild. Routes only
delegate to the index service.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_services
from core.service_container import AppServices
from models.schema import IndexStatus, SourceSummary

router = APIRouter(prefix="/index")


@router.get("/status")
def index_status(services: AppServices = Depends(get_services)) -> IndexStatus:
    return services.index.status()


@router.get("/sources")
def index_sources(services: AppServices = Depends(get_services)) -> list[SourceSummary]:
    return services.index.source_summaries()


@router.post("/pause")
def index_pause(services: AppServices = Depends(get_services)) -> IndexStatus:
    """Stops reading file contents until resumed; finishes the file in progress first."""
    services.index.set_paused(True)
    return services.index.status()


@router.post("/resume")
def index_resume(services: AppServices = Depends(get_services)) -> IndexStatus:
    services.index.set_paused(False)
    return services.index.status()


@router.post("/rebuild")
def index_rebuild(services: AppServices = Depends(get_services)) -> IndexStatus:
    """Re-reads every file from scratch in the background."""
    services.index.rebuild()
    return services.index.status()
