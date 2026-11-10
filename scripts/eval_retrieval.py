"""
Benchmarks retrieval on a small labelled corpus (tests/fixtures/eval_corpus): indexes it into
a throwaway store, then compares vector-only search with hybrid (vector + keyword) search on
recall@1, recall@5, MRR and query latency. Prints a Markdown table. Does not touch the user's
real index or settings.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "fixtures" / "eval_corpus"
os.environ.setdefault("NIMBUS_HOME", tempfile.mkdtemp(prefix="nimbus-eval-"))
sys.path.insert(0, str(ROOT))

from core.embedder import get_embedder  # noqa: E402
from core.indexer import Indexer  # noqa: E402
from core.logger import get_logger  # noqa: E402
from core.retriever import Retriever  # noqa: E402
from core.vector_store import VectorStore  # noqa: E402
from models.schema import SearchResult  # noqa: E402
from tools.file_tools import rank_unique_files  # noqa: E402

logger = get_logger(__name__)

TOP_K = 5
Search = Callable[[str], list[SearchResult]]


def build_index(store_dir: Path) -> tuple[Retriever, VectorStore, float]:
    """Indexes every corpus document; returns the retriever, its store and files indexed per second."""
    store = VectorStore(store_dir / "search.db")
    store.connect()
    embedder = get_embedder()
    embedder.load()
    indexer = Indexer(store, embedder)
    documents = sorted(p for p in CORPUS.iterdir() if p.suffix in {".txt", ".md"})
    start = time.perf_counter()
    for path in documents:
        indexer.index_file(path)
    store.optimize()
    return Retriever(store, embedder), store, len(documents) / (time.perf_counter() - start)


def score(search: Search, queries: list[dict[str, str]]) -> dict[str, float]:
    """recall@1, recall@5, MRR and mean latency for one search strategy."""
    hits_at_1 = hits_at_k = reciprocal_ranks = elapsed = 0.0
    for case in queries:
        start = time.perf_counter()
        ranked = [ref.file_name for ref in rank_unique_files(search(case["query"]))]
        elapsed += time.perf_counter() - start
        rank = ranked.index(case["expected"]) + 1 if case["expected"] in ranked[:TOP_K] else None
        hits_at_1 += rank == 1
        hits_at_k += rank is not None
        reciprocal_ranks += 1 / rank if rank else 0.0
    count = len(queries)
    return {
        "recall@1": hits_at_1 / count,
        f"recall@{TOP_K}": hits_at_k / count,
        "MRR": reciprocal_ranks / count,
        "ms/query": elapsed / count * 1000,
    }


def main() -> None:
    queries = json.loads((CORPUS / "queries.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as store_dir:
        retriever, store, files_per_second = build_index(Path(store_dir))
        semantic = score(lambda q: retriever.retrieve_semantic_only(q, top_k=TOP_K * 4), queries)
        hybrid = score(lambda q: retriever.retrieve(q, top_k=TOP_K * 4), queries)
        store.close()
    print(f"Corpus: {len(queries)} queries · indexing {files_per_second:.1f} files/s\n")
    print("| Strategy | " + " | ".join(semantic) + " |")
    print("|---|" + "---|" * len(semantic))
    for name, result in (("Vector only", semantic), ("Hybrid (vector + BM25, RRF)", hybrid)):
        print(
            f"| {name} | " + " | ".join(f"{v:.2f}" if k != "ms/query" else f"{v:.1f}" for k, v in result.items()) + " |"
        )


if __name__ == "__main__":
    main()
