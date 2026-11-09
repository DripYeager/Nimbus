"""
Command-line indexing for development: indexes one folder synchronously and reports how many
files and chunks landed. Uses the same rules and indexer as the app; does not start the watcher,
the API or any UI.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import get_settings  # noqa: E402
from core.directory_scanner import scan_source  # noqa: E402
from core.embedder import get_embedder  # noqa: E402
from core.exceptions import NimbusError  # noqa: E402
from core.index_rules import IndexRules  # noqa: E402
from core.indexer import Indexer  # noqa: E402
from core.logger import get_logger  # noqa: E402
from core.vector_store import VectorStore  # noqa: E402
from models.schema import IndexSource  # noqa: E402

logger = get_logger(__name__)


def index_folder(root: Path) -> tuple[int, int]:
    """Indexes every content file under root; returns (files indexed, chunks written)."""
    settings = get_settings().model_copy(update={"sources": [IndexSource(path=root)]})
    rules = IndexRules.from_settings(settings)
    store = VectorStore()
    store.connect()
    store.ensure_compatible(settings.embedding_model)
    indexer = Indexer(store, get_embedder())
    files = chunks = 0
    for scanned in scan_source(root, rules):
        if not rules.should_read_contents(scanned.path, scanned.size_bytes):
            continue
        try:
            chunks += indexer.index_file(scanned.path)
            files += 1
        except NimbusError as e:
            logger.warning("Skipped file", extra={"path": str(scanned.path), "error": str(e)})
    store.optimize()
    return files, chunks


def main() -> None:
    """Parses the target folder from argv and indexes it."""
    parser = argparse.ArgumentParser(description="Index a folder into Nimbus's local search index.")
    parser.add_argument("path", type=Path, help="Folder to index")
    args = parser.parse_args()
    if not args.path.is_dir():
        sys.exit(f"Not a folder: {args.path}")
    start = time.monotonic()
    files, chunks = index_folder(args.path.resolve())
    logger.info(
        "Indexing finished", extra={"files": files, "chunks": chunks, "seconds": round(time.monotonic() - start, 1)}
    )


if __name__ == "__main__":
    main()
