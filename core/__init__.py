"""Engine internals: logging, exceptions, indexing, retrieval, query orchestration."""

from __future__ import annotations

from core.exceptions import (
    AppLaunchError,
    IndexingError,
    NimbusError,
    ParsingError,
    ProviderError,
    QueryError,
)
from core.document_parser import extract_document_text, parse_document
from core.embedder import Embedder, get_embedder
from core.indexer import Indexer
from core.intent_router import classify_intent
from core.logger import get_logger
from core.ocr_fallback import extract_text_with_ocr
from core.query_engine import QueryEngine
from core.retriever import Retriever
from core.text_chunker import chunk_text
from core.vector_store import VectorStore

__all__ = [
    "NimbusError",
    "IndexingError",
    "ParsingError",
    "QueryError",
    "ProviderError",
    "AppLaunchError",
    "get_logger",
    "VectorStore",
    "Embedder",
    "get_embedder",
    "chunk_text",
    "parse_document",
    "extract_document_text",
    "extract_text_with_ocr",
    "Indexer",
    "Retriever",
    "classify_intent",
    "QueryEngine",
]
