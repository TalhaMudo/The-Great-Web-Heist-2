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

import ollama as _ollama

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

EMBED_MODEL = "nomic-embed-text"


# ---------------------------------------------------------------------------
# Wikipedia fetching — tries full extract first, summary as fallback
# ---------------------------------------------------------------------------

MAX_RETRIES = 4
RETRY_BACKOFF = [2, 5, 10, 20]


def _request_with_retry(url: str, timeout: int = 20) -> bytes:
    """GET *url* with automatic retry + exponential backoff on 429."""
    req = urllib.request.Request(url, headers={"User-Agent": "RAG-HW3-Bot/1.0"})
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF[attempt]
                logger.warning("429 rate-limited on %s — waiting %ds (attempt %d)", url[:80], wait, attempt + 1)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"Max retries exceeded for {url}")


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
    try:
        raw = _request_with_retry(url)
        data = json.loads(raw.decode())
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
    try:
        raw = _request_with_retry(url2, timeout=15)
        data = json.loads(raw.decode())
        return data.get("extract", "")
    except Exception:
        logger.exception("All Wikipedia APIs failed for: %s", title)
    return ""


# ---------------------------------------------------------------------------
# Ollama embedding helper (uses the ``ollama`` Python library)
# ---------------------------------------------------------------------------

def _check_ollama_available() -> bool:
    """Quick health check for Ollama."""
    try:
        _ollama.list()
        return True
    except Exception:
        return False


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts using the Ollama embed endpoint."""
    if not texts:
        return []
    resp = _ollama.embed(model=EMBED_MODEL, input=texts)
    return resp["embeddings"]


def embed_single(text: str) -> list[float]:
    return embed_texts([text])[0]


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
    """Ingest every entity in PEOPLE and PLACES lists.

    Skips entities that already have chunks in ChromaDB so re-running
    only fills in the gaps (e.g. after a 429 rate-limit failure).
    """
    from .chroma_store import entity_chunk_count

    if not _check_ollama_available():
        raise RuntimeError(
            "Ollama is not reachable at http://localhost:11434. "
            "Start Ollama and ensure 'nomic-embed-text' is pulled."
        )

    p_col = people_collection()
    l_col = places_collection()

    results: list[dict[str, Any]] = []
    total = len(PEOPLE) + len(PLACES)

    MIN_GOOD_CHUNKS = 3

    for i, name in enumerate(PEOPLE, 1):
        existing = entity_chunk_count(p_col, name)
        if existing >= MIN_GOOD_CHUNKS:
            logger.info("[%d/%d] Skipping %s (already %d chunks)", i, total, name, existing)
            results.append({"entity": name, "category": "person", "status": "ok", "chunks": existing})
            continue
        if existing > 0:
            logger.info("[%d/%d] Re-ingesting %s (only %d chunks, likely summary-only)", i, total, name, existing)
        else:
            logger.info("[%d/%d] Ingesting person: %s", i, total, name)
        try:
            results.append(ingest_entity(name, "person", chunk_size, overlap))
        except Exception as exc:
            logger.exception("Failed %s", name)
            results.append({"entity": name, "category": "person", "status": f"error: {exc}", "chunks": 0})
        time.sleep(1.5)

    for i, name in enumerate(PLACES, len(PEOPLE) + 1):
        existing = entity_chunk_count(l_col, name)
        if existing >= MIN_GOOD_CHUNKS:
            logger.info("[%d/%d] Skipping %s (already %d chunks)", i, total, name, existing)
            results.append({"entity": name, "category": "place", "status": "ok", "chunks": existing})
            continue
        if existing > 0:
            logger.info("[%d/%d] Re-ingesting %s (only %d chunks, likely summary-only)", i, total, name, existing)
        else:
            logger.info("[%d/%d] Ingesting place: %s", i, total, name)
        try:
            results.append(ingest_entity(name, "place", chunk_size, overlap))
        except Exception as exc:
            logger.exception("Failed %s", name)
            results.append({"entity": name, "category": "place", "status": f"error: {exc}", "chunks": 0})
        time.sleep(1.5)

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
