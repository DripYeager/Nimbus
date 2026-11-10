from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

import config.settings as settings_module
from config.settings import Settings
from core.embedder import Embedder
from core.file_catalog import FileCatalog
from core.index_service import IndexService
from core.indexer import Indexer
from core.vector_store import VectorStore
from models.chat import ToolResult
from models.schema import IndexSource, SourceRef
from tests.core.agent_test_support import RecordingTool, simple_spec
from tests.core.index_service_helpers import ServiceFactory
from tools.registry import Tool, ToolRegistry


@pytest.fixture
def synchronous_scans(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runs every rescan on the calling thread, so a test sees its results immediately."""
    monkeypatch.setattr(IndexService, "rescan", IndexService._scan_all_sources)


@pytest.fixture
def docs(tmp_path: Path) -> Path:
    folder = tmp_path / "Docs"
    folder.mkdir()
    return folder


@pytest.fixture
def configure(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    def apply(*sources: IndexSource, exclude: list[str] | None = None) -> None:
        settings = Settings(_env_file=None, sources=list(sources), exclude_patterns=exclude or [], index_throttle_ms=0)
        monkeypatch.setattr(settings_module, "_settings", settings)

    return apply


@pytest.fixture
def catalog(tmp_path: Path) -> Iterator[FileCatalog]:
    opened = FileCatalog(tmp_path / "catalog.db")
    opened.connect()
    yield opened
    opened.close()


@pytest.fixture
def store(tmp_path: Path) -> VectorStore:
    opened = VectorStore(db_path=tmp_path / "search.db")
    opened.connect()
    return opened


@pytest.fixture
def embedder(mocker: MockerFixture) -> Mock:
    fake = mocker.Mock(spec=Embedder)
    fake.embed.side_effect = lambda texts: [[1.0, 0.0, 0.0, 0.0] for _ in texts]
    return fake


@pytest.fixture
def make_service(
    catalog: FileCatalog, store: VectorStore, embedder: Mock, synchronous_scans: None
) -> Iterator[ServiceFactory]:
    built: list[IndexService] = []

    def build() -> IndexService:
        built.append(IndexService(catalog, store, Indexer(store, embedder)))
        return built[-1]

    yield build
    for service in built:
        service.stop()


@pytest.fixture
def service(configure: Callable[..., None], docs: Path, make_service: ServiceFactory) -> IndexService:
    configure(IndexSource(path=docs))
    return make_service()


@pytest.fixture
def lookup() -> RecordingTool:
    source = SourceRef(file_name="a.txt", file_path="C:/a.txt", score=1)
    return RecordingTool(ToolResult(content="found it", sources=[source]))


@pytest.fixture
def launch() -> RecordingTool:
    return RecordingTool(ToolResult(content="launched"))


@pytest.fixture
def registry(lookup: RecordingTool, launch: RecordingTool) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(Tool(simple_spec("lookup"), lookup, lambda a: "Looked something up"))
    registry.register(Tool(simple_spec("launch"), launch, lambda a: "Launch the thing", requires_confirmation=True))
    return registry
