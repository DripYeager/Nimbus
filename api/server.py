"""
FastAPI app for the query and index-control endpoints. Binding to 127.0.0.1 only happens
wherever uvicorn is actually launched (app_runtime.py, Phase 3) — this module only defines
routes. Routes delegate straight to QueryEngine and Indexer; no business logic lives here.
"""

from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from config.settings import get_settings
from core.embedder import get_embedder
from core.exceptions import NimbusError
from core.file_watcher import IndexingState
from core.indexer import Indexer
from core.query_engine import QueryEngine
from core.retriever import Retriever
from core.vector_store import VectorStore
from llm.provider import get_provider
from models.schema import IndexStatus, QueryDone, QueryFailed, QueryRequest, QueryResponse, QueryStarted, QueryToken

API_VERSION = "0.1.0"

_rebuild_lock = threading.Lock()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Builds the shared store/retriever/provider/engine/indexing-state once per process, reusing
    anything app_runtime already attached to app.state before startup so the watcher and the API
    share the same Indexer and IndexingState instead of independent copies."""
    if not hasattr(app.state, "indexing_state"):
        app.state.indexing_state = IndexingState()
    if hasattr(app.state, "query_engine"):
        yield
        return
    store = VectorStore()
    store.connect()
    embedder = get_embedder()
    provider = get_provider(get_settings())
    app.state.store = store
    app.state.indexer = Indexer(store, embedder)
    app.state.query_engine = QueryEngine(Retriever(store, embedder), provider, store)
    yield


app = FastAPI(title="Nimbus", lifespan=_lifespan)


class RebuildRequest(BaseModel):
    paths: list[str] | None = None


def get_query_engine(request: Request) -> QueryEngine:
    """Returns the shared QueryEngine built at startup — overridable in tests via dependency_overrides."""
    return request.app.state.query_engine


def get_indexer(request: Request) -> Indexer:
    """Returns the shared Indexer built at startup — overridable in tests via dependency_overrides."""
    return request.app.state.indexer


@app.exception_handler(NimbusError)
async def _handle_nimbus_error(request: Request, exc: NimbusError) -> JSONResponse:
    """Converts any domain error into the API's documented {error, type} shape."""
    return JSONResponse(status_code=502, content={"error": str(exc), "type": type(exc).__name__})


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok", "version": API_VERSION}


@app.post("/query", response_model=None)
def query(body: QueryRequest, engine: QueryEngine = Depends(get_query_engine)) -> QueryResponse | StreamingResponse:
    """Routes a request through QueryEngine; streams per-token SSE events if stream=true."""
    if not body.stream:
        return engine.handle_query(body.text)
    return StreamingResponse(_stream_query_events(engine, body.text), media_type="text/event-stream")


@app.get("/downloads/today")
def downloads_today(engine: QueryEngine = Depends(get_query_engine)) -> QueryResponse:
    """Summarizes today's downloads directly — there's no free-text query to classify."""
    return engine.handle_downloads_today()


@app.post("/index/rebuild")
def index_rebuild(
    body: RebuildRequest, background_tasks: BackgroundTasks, indexer: Indexer = Depends(get_indexer)
) -> dict[str, bool]:
    """Schedules a reindex in the background; rejects a second call while one is already running."""
    paths = _resolve_and_validate_paths(body.paths)
    if not _rebuild_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A rebuild is already running.")
    background_tasks.add_task(_run_rebuild, indexer, paths)
    return {"started": True}


@app.post("/index/pause")
def index_pause(request: Request) -> IndexStatus:
    """Pauses background indexing — file_watcher.py checks this flag before processing any event."""
    request.app.state.indexing_state.is_paused = True
    return _index_status(request)


@app.post("/index/resume")
def index_resume(request: Request) -> IndexStatus:
    """Resumes background indexing previously paused via /index/pause."""
    request.app.state.indexing_state.is_paused = False
    return _index_status(request)


def _index_status(request: Request) -> IndexStatus:
    """Builds the current IndexStatus from the shared IndexingState file_watcher.py maintains."""
    state = request.app.state.indexing_state
    return IndexStatus(
        total_files=state.total_files,
        indexed_files=state.indexed_files,
        pending=state.pending_files,
        is_paused=state.is_paused,
        last_error=None,
    )


def _resolve_and_validate_paths(raw_paths: list[str] | None) -> list[Path]:
    """Rejects any requested path outside the configured watched directories (Section 17.4)."""
    watched = [d.resolve() for d in get_settings().watched_dirs]
    if raw_paths is None:
        return watched
    paths = [Path(p).resolve() for p in raw_paths]
    for path in paths:
        if not any(path == w or w in path.parents for w in watched):
            raise HTTPException(status_code=400, detail=f"{path} is not inside a watched directory.")
    return paths


def _run_rebuild(indexer: Indexer, paths: list[Path]) -> None:
    """Runs the actual reindex in the background, always releasing the lock when it's done."""
    try:
        for path in paths:
            indexer.index_directory(path)
    finally:
        _rebuild_lock.release()


_SSE_EVENT_NAMES: dict[type[BaseModel], str] = {
    QueryStarted: "started",
    QueryToken: "token",
    QueryDone: "done",
    QueryFailed: "error",
}


def _sse_event(event: QueryStarted | QueryToken | QueryDone | QueryFailed) -> str:
    """Serializes one query-stream event as a named SSE frame."""
    name = _SSE_EVENT_NAMES[type(event)]
    return f"event: {name}\ndata: {event.model_dump_json()}\n\n"


def _stream_query_events(engine: QueryEngine, text: str) -> Generator[str, None, None]:
    """Runs the query stream, converting a mid-stream NimbusError into a graceful error event
    instead of dropping the connection — the overlay's thinking indicator needs a real event to
    stop on, not a silently closed stream."""
    try:
        for event in engine.stream_query(text):
            yield _sse_event(event)
    except NimbusError as e:
        yield _sse_event(QueryFailed(message=str(e)))
