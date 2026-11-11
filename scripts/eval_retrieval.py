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

from config.settings import get_settings  # noqa: E402
from core.embedder import get_embedder  # noqa: E402
from core.indexer import Indexer  # noqa: E402
from core.logger import get_logger  # noqa: E402
from core.reranker import Reranker  # noqa: E402
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


QUERY_SETS = (("Direct questions", "queries.json"), ("Paraphrased questions", "queries_hard.json"))


def main() -> None:
    """Scores each strategy on both question sets and prints one Markdown table per set."""
    with tempfile.TemporaryDirectory() as store_dir:
        retriever, store, files_per_second = build_index(Path(store_dir))
        reranker = Reranker(get_settings().rerank_model, get_settings().embedding_threads)
        reranker.load()
        reranked = Retriever(store, get_embedder(), reranker)
        strategies: dict[str, Search] = {
            "Vector only": lambda q: retriever.retrieve_semantic_only(q, top_k=TOP_K * 4),
            "Hybrid (vector + BM25, RRF)": lambda q: retriever.retrieve(q, top_k=TOP_K * 4),
            "Hybrid + cross-encoder rerank": lambda q: reranked.retrieve(q, top_k=TOP_K * 4),
        }
        print(f"Indexing {files_per_second:.1f} files/s · reranker {get_settings().rerank_model}")
        for title, file_name in QUERY_SETS:
            queries = json.loads((CORPUS / file_name).read_text(encoding="utf-8"))
            _print_table(f"{title} ({len(queries)})", {name: score(fn, queries) for name, fn in strategies.items()})
        store.close()


def _print_table(title: str, results: dict[str, dict[str, float]]) -> None:
    columns = next(iter(results.values()))
    print(f"\n{title}\n\n| Strategy | " + " | ".join(columns) + " |")
    print("|---|" + "---|" * len(columns))
    for name, result in results.items():
        cells = " | ".join(f"{v:.2f}" if k != "ms/query" else f"{v:.0f}" for k, v in result.items())
        print(f"| {name} | {cells} |")


if __name__ == "__main__":
    main()
