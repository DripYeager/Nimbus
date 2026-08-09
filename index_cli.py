"""Command-line entry point: indexes a directory tree into LanceDB and reports how many chunks landed."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.embedder import get_embedder
from core.exceptions import NimbusError
from core.indexer import Indexer
from core.logger import get_logger
from core.vector_store import VectorStore

logger = get_logger(__name__)


def main() -> None:
    """Parses the target directory from argv, indexes it, and prints the chunk count."""
    parser = argparse.ArgumentParser(description="Index a directory into Nimbus's local vector store.")
    parser.add_argument("path", type=Path, help="Directory to index")
    args = parser.parse_args()

    if not args.path.is_dir():
        print(f"Not a directory: {args.path}", file=sys.stderr)
        sys.exit(1)

    store = VectorStore()
    store.connect()
    try:
        total = Indexer(store, get_embedder()).index_directory(args.path)
    except NimbusError as e:
        print(f"Indexing failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Indexed {total} chunk(s) from {args.path}")


if __name__ == "__main__":
    main()
