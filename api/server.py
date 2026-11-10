"""
The FastAPI app: mounts the chat, index, settings and app routes, and maps domain errors to
a consistent {error, type} JSON shape. Binding to 127.0.0.1 happens wherever uvicorn is
started (core/app_runtime.py). Holds no business logic.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api import app_routes, chat_routes, index_routes, ollama_routes, settings_routes
from core.exceptions import (
    AppLaunchError,
    ConversationNotFoundError,
    NimbusError,
    SecretStoreError,
    SettingsError,
    ToolError,
)
from core.service_container import AppServices

API_VERSION = "2.1.0"

# Errors the caller can fix by changing their request; everything else is the engine's fault.
CLIENT_ERROR_STATUS: dict[type[NimbusError], int] = {
    SettingsError: 400,
    SecretStoreError: 400,
    ToolError: 400,
    AppLaunchError: 400,
    ConversationNotFoundError: 404,
}


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Builds and starts the engine when the API runs on its own (uvicorn api.server:app). The
    desktop app builds its services first and attaches them, so this is then a no-op."""
    if hasattr(app.state, "services"):
        yield
        return
    services = AppServices.build()
    services.start()
    app.state.services = services
    try:
        yield
    finally:
        services.stop()


app = FastAPI(title="Nimbus", version=API_VERSION, lifespan=_lifespan)
app.include_router(chat_routes.router)
app.include_router(index_routes.router)
app.include_router(settings_routes.router)
app.include_router(app_routes.router)
app.include_router(ollama_routes.router)


@app.exception_handler(NimbusError)
async def _handle_nimbus_error(request: Request, exc: NimbusError) -> JSONResponse:
    """Converts any domain error into the documented {error, type} shape."""
    status_code = next((code for cls, code in CLIENT_ERROR_STATUS.items() if isinstance(exc, cls)), 502)
    return JSONResponse(status_code=status_code, content={"error": str(exc), "type": type(exc).__name__})


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok", "version": API_VERSION}
