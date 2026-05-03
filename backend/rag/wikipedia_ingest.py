"""Fetch Wikipedia articles for all entities, chunk, embed with Ollama
nomic-embed-text, and store into ChromaDB.

Run standalone:
    python -m backend.rag.wikipedia_ingest [--chunk-size 500] [--overlap 50]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

from .chroma_store import (
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
# Wikipedia fetching via the MediaWiki REST API (plain text extract)
# ---------------------------------------------------------------------------

def fetch_wikipedia_text(title: str) -> str:
    """Return the plain-text extract for a Wikipedia article title."""
    encoded = urllib.parse.quote(title.replace(" ", "_"))
    url = (
        f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "RAG-HW3-Bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            extract = data.get("extract", "")
            if extract:
                return extract
    except Exception:
        pass

    # Fallback: full extract via action API
    params = urllib.parse.urlencode({
        "action": "query",
        "titles": title,
        "prop": "extracts",
        "explaintext": "1",
        "format": "json",
    })
    url2 = f"https://en.wikipedia.org/w/api.php?{params}"
    req2 = urllib.request.Request(url2, headers={"User-Agent": "RAG-HW3-Bot/1.0"})
    try:
        with urllib.request.urlopen(req2, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                return page.get("extract", "")
    except Exception:
        logger.exception("Failed to fetch Wikipedia article: %s", title)
    return ""


# ---------------------------------------------------------------------------
# Ollama embedding helper
# ---------------------------------------------------------------------------

def embed_texts(texts: list[str]) -> list[list[float]]:
    """Call Ollama /api/embed to get embeddings for a batch of texts."""
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
    return embed_texts([text])[0]


# ---------------------------------------------------------------------------
# Main ingestion logic
# ---------------------------------------------------------------------------

def ingest_entity(
    name: str,
    category: str,
    chunk_size: int,
    overlap: int,
) -> dict[str, Any]:
    """Fetch, chunk, embed, and store one entity. Returns summary dict."""
    text = fetch_wikipedia_text(name)
    if not text:
        logger.warning("No text for %s", name)
        return {"entity": name, "category": category, "status": "no_text", "chunks": 0}

    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        return {"entity": name, "category": category, "status": "no_chunks", "chunks": 0}

    embeddings = embed_texts(chunks)
    col = people_collection() if category == "person" else places_collection()
    n = upsert_chunks(col, entity_name=name, chunks=chunks, embeddings=embeddings)
    logger.info("Ingested %s (%s): %d chunks", name, category, n)
    return {"entity": name, "category": category, "status": "ok", "chunks": n}


def ingest_all(chunk_size: int = 500, overlap: int = 50) -> list[dict[str, Any]]:
    """Ingest every entity in PEOPLE and PLACES lists."""
    results: list[dict[str, Any]] = []
    for name in PEOPLE:
        try:
            results.append(ingest_entity(name, "person", chunk_size, overlap))
        except Exception as exc:
            logger.exception("Failed %s", name)
            results.append({"entity": name, "category": "person", "status": f"error: {exc}", "chunks": 0})
    for name in PLACES:
        try:
            results.append(ingest_entity(name, "place", chunk_size, overlap))
        except Exception as exc:
            logger.exception("Failed %s", name)
            results.append({"entity": name, "category": "place", "status": f"error: {exc}", "chunks": 0})
    return results


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Wikipedia data for RAG")
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--overlap", type=int, default=50)
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
