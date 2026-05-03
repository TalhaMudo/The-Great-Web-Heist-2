"""Fetch Wikipedia articles for all entities, chunk, embed with Ollama
nomic-embed-text, and store into ChromaDB.

Run standalone:
    python -m backend.rag.wikipedia_ingest
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .chroma_store import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    chunk_text,
    people_collection,
    places_collection,
    upsert_chunks,
)
from .entities import PEOPLE, PLACES

logger = logging.getLogger(__name__)

OLLAMA_BASE = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"


# ---------------------------------------------------------------------------
# Wikipedia fetching — tries full extract first, summary as fallback
# ---------------------------------------------------------------------------

def fetch_wikipedia_text(title: str) -> str:
    """Return the plain-text extract for a Wikipedia article title."""

    # Try the action API for full content first
    params = urllib.parse.urlencode({
        "action": "query",
        "titles": title,
        "prop": "extracts",
        "explaintext": "1",
        "format": "json",
    })
    url = f"https://en.wikipedia.org/w/api.php?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "RAG-HW3-Bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                extract = page.get("extract", "")
                if extract and len(extract) > 50:
                    return extract
    except Exception:
        logger.warning("Action API failed for %s, trying summary API", title)

    # Fallback: REST summary API
    encoded = urllib.parse.quote(title.replace(" ", "_"))
    url2 = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    req2 = urllib.request.Request(url2, headers={"User-Agent": "RAG-HW3-Bot/1.0"})
    try:
        with urllib.request.urlopen(req2, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return data.get("extract", "")
    except Exception:
        logger.exception("All Wikipedia APIs failed for: %s", title)
    return ""


# ---------------------------------------------------------------------------
# Ollama embedding helper
# ---------------------------------------------------------------------------

def _check_ollama_available() -> bool:
    """Quick health check for Ollama."""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Call Ollama /api/embed to get embeddings for a batch of texts.
    Embeds one at a time if batch fails (some Ollama versions have limits)."""
    if not texts:
        return []

    # Try batch first
    try:
        return _embed_batch(texts)
    except Exception:
        logger.warning("Batch embedding failed, falling back to one-at-a-time")

    # Fallback: embed one at a time
    results: list[list[float]] = []
    for text in texts:
        results.append(_embed_batch([text])[0])
    return results


def _embed_batch(texts: list[str]) -> list[list[float]]:
    url = f"{OLLAMA_BASE}/api/embed"
    payload = json.dumps({"model": EMBED_MODEL, "input": texts}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    return data["embeddings"]


def embed_single(text: str) -> list[float]:
    return _embed_batch([text])[0]


# ---------------------------------------------------------------------------
# Main ingestion logic
# ---------------------------------------------------------------------------

def ingest_entity(
    name: str,
    category: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> dict[str, Any]:
    """Fetch, chunk, embed, and store one entity. Returns summary dict."""
    text = fetch_wikipedia_text(name)
    if not text:
        logger.warning("No text for %s", name)
        return {"entity": name, "category": category, "status": "no_text", "chunks": 0}

    # Prepend entity name for better context in chunks
    text = f"{name}\n\n{text}"

    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        return {"entity": name, "category": category, "status": "no_chunks", "chunks": 0}

    embeddings = embed_texts(chunks)
    col = people_collection() if category == "person" else places_collection()
    n = upsert_chunks(col, entity_name=name, chunks=chunks, embeddings=embeddings)
    logger.info("Ingested %s (%s): %d chunks", name, category, n)
    return {"entity": name, "category": category, "status": "ok", "chunks": n}


def ingest_all(
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[dict[str, Any]]:
    """Ingest every entity in PEOPLE and PLACES lists."""
    if not _check_ollama_available():
        raise RuntimeError(
            "Ollama is not reachable at http://localhost:11434. "
            "Start Ollama and ensure 'nomic-embed-text' is pulled."
        )

    results: list[dict[str, Any]] = []
    total = len(PEOPLE) + len(PLACES)
    for i, name in enumerate(PEOPLE, 1):
        logger.info("[%d/%d] Ingesting person: %s", i, total, name)
        try:
            results.append(ingest_entity(name, "person", chunk_size, overlap))
        except Exception as exc:
            logger.exception("Failed %s", name)
            results.append({"entity": name, "category": "person", "status": f"error: {exc}", "chunks": 0})
        time.sleep(0.1)

    for i, name in enumerate(PLACES, len(PEOPLE) + 1):
        logger.info("[%d/%d] Ingesting place: %s", i, total, name)
        try:
            results.append(ingest_entity(name, "place", chunk_size, overlap))
        except Exception as exc:
            logger.exception("Failed %s", name)
            results.append({"entity": name, "category": "place", "status": f"error: {exc}", "chunks": 0})
        time.sleep(0.1)

    return results


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Wikipedia data for RAG")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    results = ingest_all(chunk_size=args.chunk_size, overlap=args.overlap)

    ok = sum(1 for r in results if r["status"] == "ok")
    total_chunks = sum(r["chunks"] for r in results)
    print(f"\nDone. {ok}/{len(results)} entities ingested, {total_chunks} total chunks.")
    failed = [r for r in results if r["status"] != "ok"]
    if failed:
        print("Failed entities:")
        for r in failed:
            print(f"  - {r['entity']}: {r['status']}")


if __name__ == "__main__":
    main()
