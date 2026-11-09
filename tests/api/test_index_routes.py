from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.exceptions import IndexingError
from core.service_container import AppServices
from models.schema import IndexStatus, SourceSummary


@pytest.fixture(autouse=True)
def status(services: AppServices) -> IndexStatus:
    status = IndexStatus(cataloged_files=10, indexed_files=4, pending_files=2)
    services.index.status.return_value = status
    return status


def test_index_status_returns_the_snapshot(client: TestClient) -> None:
    body = client.get("/index/status").json()

    assert (body["cataloged_files"], body["indexed_files"], body["pending_files"]) == (10, 4, 2)


def test_index_sources_returns_per_folder_counts(client: TestClient, services: AppServices) -> None:
    services.index.source_summaries.return_value = [
        SourceSummary(path="C:/Docs", include_contents=True, exists=True, file_count=10, indexed_count=4)
    ]

    assert client.get("/index/sources").json()[0]["path"] == "C:/Docs"


def test_index_pause_pauses_indexing(client: TestClient, services: AppServices) -> None:
    response = client.post("/index/pause")

    services.index.set_paused.assert_called_once_with(True)
    assert response.status_code == 200


def test_index_resume_resumes_indexing(client: TestClient, services: AppServices) -> None:
    client.post("/index/resume")

    services.index.set_paused.assert_called_once_with(False)


def test_index_rebuild_starts_a_rebuild(client: TestClient, services: AppServices) -> None:
    client.post("/index/rebuild")

    services.index.rebuild.assert_called_once()


def test_index_rebuild_reports_a_failure_as_an_error_body(client: TestClient, services: AppServices) -> None:
    services.index.rebuild.side_effect = IndexingError("the index is locked")

    response = client.post("/index/rebuild")

    assert response.status_code == 502
    assert response.json()["error"] == "the index is locked"
