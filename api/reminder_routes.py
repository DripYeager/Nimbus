"""
HTTP route the tray polls for reminders that have fallen due. Each one is handed out once.
Routes only delegate; the store lives in core/reminders.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_services
from core.service_container import AppServices
from models.api import DueReminder

router = APIRouter(prefix="/reminders")


@router.get("/due")
def due_reminders(services: AppServices = Depends(get_services)) -> list[DueReminder]:
    """Reminders whose time has come; they won't be returned again."""
    return [DueReminder(text=r.text, due=r.due) for r in services.reminders.take_due()]
