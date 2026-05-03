"""ChromaDB vector store wrapper with two collections (people / places),
chunking utilities, and dual search (semantic + keyword)."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger(__name__)

CHROMA_DIR = Path(__file__).resolve().parent.parent.parent / "chroma_data"

PEOPLE_COLLECTION = "people_chunks"
PLACES_COLLECTION = "places_chunks"

DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split *text* into fixed-size character chunks with overlap."""
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


# ---------------------------------------------------------------------------
# Chroma client singleton
# ---------------------------------------------------------------------------

_client: chromadb.ClientAPI | None = None


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def get_collection(name: str) -> chromadb.Collection:
    client = _get_client()
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def people_collection() -> chromadb.Collection:
    return get_collection(PEOPLE_COLLECTION)


def places_collection() -> chromadb.Collection:
    return get_collection(PLACES_COLLECTION)


# ---------------------------------------------------------------------------
# Upsert helpers
# ---------------------------------------------------------------------------

def upsert_chunks(
    collection: chromadb.Collection,
    entity_name: str,
    chunks: list[str],
    embeddings: list[list[float]],
) -> int:
    """Add chunks for a single entity.  Returns number of chunks stored."""
    if not chunks:
        return 0
    ids = [f"{entity_name}::chunk_{i}" for i in range(len(chunks))]
    metadatas = [{"entity": entity_name, "chunk_index": i} for i in range(len(chunks))]
    collection.upsert(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
    )
    return len(chunks)


# ---------------------------------------------------------------------------
# Search helpers
# ---------------------------------------------------------------------------

def semantic_search(
    collection: chromadb.Collection,
    query_embedding: list[float],
    top_k: int = 5,
    where: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Cosine-similarity search using a pre-computed query embedding."""
    kwargs: dict[str, Any] = {
        "query_embeddings": [query_embedding],
        "n_results": top_k,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where
    try:
        results = collection.query(**kwargs)
    except Exception:
        logger.exception("ChromaDB semantic search failed")
        return []
    return _flatten_results(results)


def keyword_search(
    collection: chromadb.Collection,
    query: str,
    top_k: int = 5,
    where: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Simple substring / where-document search using ChromaDB's built-in
    ``$contains`` operator.  Falls back to empty list on errors."""
    sanitized = re.sub(r"[^a-zA-Z0-9 ]", "", query).strip()
    if not sanitized:
        return []
    kwargs: dict[str, Any] = {
        "where_document": {"$contains": sanitized},
        "n_results": top_k,
        "include": ["documents", "metadatas"],
    }
    if where:
        kwargs["where"] = where
    try:
        results = collection.get(**kwargs)
    except Exception:
        logger.exception("ChromaDB keyword search failed")
        return []
    return _flatten_get_results(results)


# ---------------------------------------------------------------------------
# Collection stats
# ---------------------------------------------------------------------------

def collection_count(collection: chromadb.Collection) -> int:
    try:
        return collection.count()
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _flatten_results(results: dict) -> list[dict[str, Any]]:
    """Convert ChromaDB query() response into a flat list of dicts."""
    out: list[dict[str, Any]] = []
    if not results or not results.get("ids"):
        return out
    ids = results["ids"][0]
    docs = (results.get("documents") or [[]])[0]
    metas = (results.get("metadatas") or [[]])[0]
    dists = (results.get("distances") or [[]])[0]
    for i, cid in enumerate(ids):
        out.append({
            "id": cid,
            "document": docs[i] if i < len(docs) else "",
            "metadata": metas[i] if i < len(metas) else {},
            "distance": dists[i] if i < len(dists) else None,
        })
    return out


def _flatten_get_results(results: dict) -> list[dict[str, Any]]:
    """Convert ChromaDB get() response into a flat list of dicts."""
    out: list[dict[str, Any]] = []
    if not results or not results.get("ids"):
        return out
    ids = results["ids"]
    docs = results.get("documents") or []
    metas = results.get("metadatas") or []
    for i, cid in enumerate(ids):
        out.append({
            "id": cid,
            "document": docs[i] if i < len(docs) else "",
            "metadata": metas[i] if i < len(metas) else {},
            "distance": None,
        })
    return out
