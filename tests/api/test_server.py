from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

import api.server as server_module
from api.server import app, get_indexer, get_query_engine
from core.embedder import get_embedder
from core.exceptions import ProviderError
from core.file_watcher import IndexingState
from core.indexer import Indexer
from core.query_engine import QueryEngine
from core.vector_store import VectorStore
from models.schema import Intent, ParsedDocument, QueryDone, QueryResponse, QueryStarted, QueryToken


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def indexing_state() -> IndexingState:
    """Injects a fresh IndexingState directly, the same way app_runtime does in the real app —
    avoids paying for the full lifespan (real VectorStore + embedder) just for these routes."""
    state = IndexingState()
    app.state.indexing_state = state
    return state


@pytest.fixture(autouse=True)
def _reset_shared_state():
    yield
    app.dependency_overrides.clear()
    if server_module._rebuild_lock.locked():
        server_module._rebuild_lock.release()


def _fake_response(**overrides: object) -> QueryResponse:
    defaults = {"answer": "an answer", "intent": Intent.GENERAL_QA, "sources": [], "used_llm": True, "elapsed_ms": 42}
    defaults.update(overrides)
    return QueryResponse(**defaults)


def test_health_returns_ok_and_a_version(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": server_module.API_VERSION}


def test_query_returns_json_when_stream_is_false(client: TestClient, mocker: MockerFixture) -> None:
    engine = mocker.Mock(spec=QueryEngine)
    engine.handle_query.return_value = _fake_response(answer="the answer")
    app.dependency_overrides[get_query_engine] = lambda: engine

    response = client.post("/query", json={"text": "hello", "stream": False})

    assert response.status_code == 200
    assert response.json()["answer"] == "the answer"
    engine.handle_query.assert_called_once_with("hello")


def _fake_stream(*tokens: str) -> list[QueryStarted | QueryToken | QueryDone]:
    started = QueryStarted(intent=Intent.GENERAL_QA, sources=[])
    return [started, *(QueryToken(text=t) for t in tokens), QueryDone(used_llm=True, elapsed_ms=12)]


def test_query_returns_sse_when_stream_is_true(client: TestClient, mocker: MockerFixture) -> None:
    engine = mocker.Mock(spec=QueryEngine)
    engine.stream_query.return_value = iter(_fake_stream("streamed answer"))
    app.dependency_overrides[get_query_engine] = lambda: engine

    response = client.post("/query", json={"text": "hello", "stream": True})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: started" in response.text
    assert "event: token" in response.text
    assert "event: done" in response.text
    assert "streamed answer" in response.text


def test_query_defaults_to_streaming_when_stream_is_omitted(client: TestClient, mocker: MockerFixture) -> None:
    engine = mocker.Mock(spec=QueryEngine)
    engine.stream_query.return_value = iter(_fake_stream("hi"))
    app.dependency_overrides[get_query_engine] = lambda: engine

    response = client.post("/query", json={"text": "hello"})

    assert response.headers["content-type"].startswith("text/event-stream")


def test_query_stream_reports_sources_in_the_started_event(client: TestClient, mocker: MockerFixture) -> None:
    engine = mocker.Mock(spec=QueryEngine)
    started = QueryStarted(intent=Intent.FILE_SEARCH, sources=[{"file_name": "a.pdf", "file_path": "C:/a.pdf", "score": 0.9}])
    engine.stream_query.return_value = iter([started, QueryDone(used_llm=False, elapsed_ms=1)])
    app.dependency_overrides[get_query_engine] = lambda: engine

    response = client.post("/query", json={"text": "hello", "stream": True})

    assert "a.pdf" in response.text


def test_query_stream_converts_a_mid_stream_nimbus_error_to_an_error_event(
    client: TestClient, mocker: MockerFixture
) -> None:
    def _raising_stream(*_args: object, **_kwargs: object):
        yield QueryStarted(intent=Intent.GENERAL_QA, sources=[])
        raise ProviderError("Ollama died mid-stream")

    engine = mocker.Mock(spec=QueryEngine)
    engine.stream_query.side_effect = _raising_stream
    app.dependency_overrides[get_query_engine] = lambda: engine

    response = client.post("/query", json={"text": "hello", "stream": True})

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "Ollama died mid-stream" in response.text


def test_query_converts_a_nimbus_error_to_the_documented_shape(client: TestClient, mocker: MockerFixture) -> None:
    engine = mocker.Mock(spec=QueryEngine)
    engine.handle_query.side_effect = ProviderError("Ollama is not running")
    app.dependency_overrides[get_query_engine] = lambda: engine

    response = client.post("/query", json={"text": "hello", "stream": False})

    assert response.status_code == 502
    assert response.json() == {"error": "Ollama is not running", "type": "ProviderError"}


def test_downloads_today_calls_handle_downloads_today_directly(client: TestClient, mocker: MockerFixture) -> None:
    engine = mocker.Mock(spec=QueryEngine)
    engine.handle_downloads_today.return_value = _fake_response(intent=Intent.DOWNLOADS_TODAY, answer="digest")
    app.dependency_overrides[get_query_engine] = lambda: engine

    response = client.get("/downloads/today")

    assert response.status_code == 200
    assert response.json()["answer"] == "digest"
    engine.handle_downloads_today.assert_called_once_with()
    engine.handle_query.assert_not_called()


def test_index_pause_marks_indexing_paused(client: TestClient, indexing_state: IndexingState) -> None:
    response = client.post("/index/pause")

    assert response.status_code == 200
    assert response.json()["is_paused"] is True
    assert indexing_state.is_paused is True


def test_index_resume_marks_indexing_not_paused(client: TestClient, indexing_state: IndexingState) -> None:
    client.post("/index/pause")

    response = client.post("/index/resume")

    assert response.status_code == 200
    assert response.json()["is_paused"] is False


def test_index_status_reports_real_counts_from_indexing_state(
    client: TestClient, indexing_state: IndexingState
) -> None:
    indexing_state.mark_indexed("a.txt")
    indexing_state.mark_indexed("b.txt")
    indexing_state.pending_files = 3

    status = client.post("/index/resume").json()

    assert status == {"total_files": 5, "indexed_files": 2, "pending": 3, "is_paused": False, "last_error": None}


def test_index_rebuild_schedules_a_background_task(client: TestClient, mocker: MockerFixture) -> None:
    app.dependency_overrides[get_indexer] = lambda: mocker.Mock(spec=Indexer)
    run_spy = mocker.patch("api.server._run_rebuild")

    response = client.post("/index/rebuild", json={})

    assert response.status_code == 200
    assert response.json() == {"started": True}
    run_spy.assert_called_once()


def test_index_rebuild_defaults_to_every_watched_dir_when_no_paths_given(
    client: TestClient, mocker: MockerFixture
) -> None:
    watched_dirs = [Path("C:/Users/test/Downloads")]
    mocker.patch("api.server.get_settings", return_value=mocker.Mock(watched_dirs=watched_dirs))
    app.dependency_overrides[get_indexer] = lambda: mocker.Mock(spec=Indexer)
    run_spy = mocker.patch("api.server._run_rebuild")

    response = client.post("/index/rebuild", json={})

    assert response.status_code == 200
    assert run_spy.call_args[0][1] == watched_dirs


def test_index_rebuild_rejects_a_path_outside_watched_dirs(client: TestClient, mocker: MockerFixture) -> None:
    mocker.patch(
        "api.server.get_settings", return_value=mocker.Mock(watched_dirs=[Path("C:/Users/test/Downloads")])
    )
    app.dependency_overrides[get_indexer] = lambda: mocker.Mock(spec=Indexer)

    response = client.post("/index/rebuild", json={"paths": ["C:/Windows/System32"]})

    assert response.status_code == 400


def test_index_rebuild_accepts_a_subdirectory_of_a_watched_dir(
    client: TestClient, mocker: MockerFixture, tmp_path: Path
) -> None:
    watched = tmp_path / "Downloads"
    (watched / "sub").mkdir(parents=True)
    mocker.patch("api.server.get_settings", return_value=mocker.Mock(watched_dirs=[watched]))
    app.dependency_overrides[get_indexer] = lambda: mocker.Mock(spec=Indexer)
    mocker.patch("api.server._run_rebuild")

    response = client.post("/index/rebuild", json={"paths": [str(watched / "sub")]})

    assert response.status_code == 200


def test_index_rebuild_returns_409_when_a_rebuild_is_already_running(
    client: TestClient, mocker: MockerFixture
) -> None:
    app.dependency_overrides[get_indexer] = lambda: mocker.Mock(spec=Indexer)
    server_module._rebuild_lock.acquire()

    response = client.post("/index/rebuild", json={})

    assert response.status_code == 409
    assert "already running" in response.json()["detail"]


def test_index_rebuild_runs_the_real_indexer_and_releases_the_lock(
    client: TestClient, mocker: MockerFixture, tmp_path: Path
) -> None:
    (tmp_path / "note.txt").write_text("hello")
    mocker.patch(
        "core.document_parser.parse_document",
        return_value=ParsedDocument(markdown_text="hello world", needs_ocr=False),
    )
    store = VectorStore(db_path=tmp_path / "index")
    store.connect()
    real_indexer = Indexer(store, get_embedder())
    app.dependency_overrides[get_indexer] = lambda: real_indexer
    mocker.patch("api.server.get_settings", return_value=mocker.Mock(watched_dirs=[tmp_path]))

    response = client.post("/index/rebuild", json={})

    assert response.status_code == 200
    assert store.count() == 1
    assert not server_module._rebuild_lock.locked()
