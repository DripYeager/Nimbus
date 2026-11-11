"""
The FastAPI app: mounts the chat, index, settings and app routes, and maps domain errors to
a consistent {error, type} JSON shape, and turns away any request that isn't addressed to this
machine or doesn't carry this run's secret (core/api_auth.py). Binding to 127.0.0.1 happens
wherever uvicorn is started (core/app_runtime.py). Holds no business logic.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from api import (
    app_routes,
    chat_routes,
    index_routes,
    mcp_routes,
    ollama_routes,
    reminder_routes,
    settings_routes,
    tool_routes,
)
from core.api_auth import BRIDGE_PATH_PREFIX, TOKEN_HEADER, is_allowed_host, is_valid_bridge_token, is_valid_token
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
# Liveness needs no secret; it says nothing beyond "running".
OPEN_PATHS = frozenset({"/health"})

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
app.include_router(reminder_routes.router)
app.include_router(tool_routes.router)
app.include_router(mcp_routes.router)


@app.middleware("http")
async def _require_local_caller(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Rejects requests addressed to another host name (a DNS-rebinding web page) and any
    request without this run's secret (another program on the PC). The MCP bridge's secret
    opens the shared /tools routes and nothing else; the app's own secret doesn't open those."""
    if not is_allowed_host(request.headers.get("host")):
        return _refused(403, "Requests must be addressed to 127.0.0.1 or localhost.")
    path = request.url.path
    presented = request.headers.get(TOKEN_HEADER)
    if path.startswith(BRIDGE_PATH_PREFIX):
        allowed = is_valid_bridge_token(presented)
    else:
        allowed = path in OPEN_PATHS or is_valid_token(presented)
    if not allowed:
        return _refused(401, "Missing or wrong Nimbus API token.")
    return await call_next(request)


def _refused(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message, "type": "Unauthorized"})


@app.exception_handler(NimbusError)
async def _handle_nimbus_error(request: Request, exc: NimbusError) -> JSONResponse:
    """Converts any domain error into the documented {error, type} shape."""
    status_code = next((code for cls, code in CLIENT_ERROR_STATUS.items() if isinstance(exc, cls)), 502)
    return JSONResponse(status_code=status_code, content={"error": str(exc), "type": type(exc).__name__})


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok", "version": API_VERSION}
