from __future__ import annotations

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from models.schema import SourceRef
from ui.overlay_sources import SourceCitations


@pytest.fixture(autouse=True, scope="session")
def _qapp():
    """QLabel/pyqtSignal machinery needs a QApplication instance to exist somewhere."""
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def citations() -> SourceCitations:
    return SourceCitations()


def test_set_sources_renders_one_link_per_source_indexed_by_position(citations: SourceCitations) -> None:
    sources = [
        SourceRef(file_name="invoice.pdf", file_path="C:/invoice.pdf", score=0.9),
        SourceRef(file_name="report.docx", file_path="C:/report.docx", score=0.7),
    ]

    citations.set_sources(sources)

    assert '<a href="0"' in citations.text()
    assert '<a href="1"' in citations.text()
    assert "invoice.pdf" in citations.text()
    assert "report.docx" in citations.text()


def test_set_sources_escapes_special_characters_in_file_names(citations: SourceCitations) -> None:
    citations.set_sources([SourceRef(file_name="A & B.pdf", file_path="C:/A & B.pdf", score=0.5)])

    assert "A &amp; B.pdf" in citations.text()


def test_clicking_a_link_opens_its_file_via_the_os_default_handler(
    citations: SourceCitations, mocker: MockerFixture
) -> None:
    startfile = mocker.patch("ui.overlay_sources.os.startfile")
    citations.set_sources([SourceRef(file_name="invoice.pdf", file_path="C:/invoice.pdf", score=0.9)])

    citations.linkActivated.emit("0")

    startfile.assert_called_once_with(Path("C:/invoice.pdf"))


def test_clicking_a_link_emits_open_failed_when_the_os_cannot_open_it(
    citations: SourceCitations, mocker: MockerFixture
) -> None:
    mocker.patch("ui.overlay_sources.os.startfile", side_effect=OSError("no association"))
    citations.set_sources([SourceRef(file_name="invoice.pdf", file_path="C:/invoice.pdf", score=0.9)])
    received = []
    citations.open_failed.connect(received.append)

    citations.linkActivated.emit("0")

    assert len(received) == 1
    assert "invoice.pdf" in received[0]


def test_clear_drops_the_source_list_backing_the_links(citations: SourceCitations) -> None:
    citations.set_sources([SourceRef(file_name="invoice.pdf", file_path="C:/invoice.pdf", score=0.9)])

    citations.clear()

    assert citations._sources == []
    assert citations.text() == ""
