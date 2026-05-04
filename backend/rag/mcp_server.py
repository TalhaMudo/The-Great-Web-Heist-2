"""MCP tool server exposing get_info_person / get_info_place.

The tools are also usable directly from the FastAPI process via
``execute_tool(name, args)`` without needing a subprocess transport.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .chroma_store import (
    keyword_search,
    people_collection,
    places_collection,
    semantic_search,
)
from .wikipedia_ingest import embed_single

logger = logging.getLogger(__name__)

TOP_K = 5


# ---------------------------------------------------------------------------
# Core retrieval functions (called by both MCP and direct invocation)
# ---------------------------------------------------------------------------

def _entity_matches(chunk_entity: str, query_name: str) -> bool:
    """Check if a chunk's entity metadata matches the queried name
    (case-insensitive, handles minor variations)."""
    if not chunk_entity:
        return False
    return chunk_entity.lower() == query_name.lower()


def _retrieve(
    collection_getter,
    name: str,
    query: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Run semantic + keyword search on a collection and return a
    formatted text block plus the raw chunk list for the UI.

    Uses a strict rule-based validation: if none of the retrieved chunks
    belong to the queried entity (checked via metadata), immediately
    returns 'No information found' regardless of what the search returned.
    This prevents the LLM from hallucinating answers about unknown entities.
    """

    col = collection_getter()
    search_text = f"{name} {query}" if query else name

    sem_results = _semantic(col, search_text, where={"entity": name})
    kw_results = _keyword(col, search_text, where={"entity": name})

    # If the exact entity filter found nothing, try unfiltered (handles
    # minor spelling variations where the LLM sends a slightly different name).
    if not sem_results and not kw_results:
        sem_results = _semantic(col, search_text, where=None)
        kw_results = _keyword(col, search_text, where=None)

    seen_ids: set[str] = set()
    merged: list[dict[str, Any]] = []
    for r in sem_results:
        rid = r["id"]
        if rid not in seen_ids:
            seen_ids.add(rid)
            r["search_type"] = "semantic"
            merged.append(r)
    for r in kw_results:
        rid = r["id"]
        if rid not in seen_ids:
            seen_ids.add(rid)
            r["search_type"] = "keyword"
            merged.append(r)

    if not merged:
        return f"No information found for '{name}'.", []

    # RULE-BASED VALIDATION: check if ANY chunk actually belongs to the
    # queried entity. If all chunks are about different entities, the
    # queried entity is not in our knowledge base — return not-found.
    has_matching_chunk = any(
        _entity_matches(r.get("metadata", {}).get("entity", ""), name)
        for r in merged
    )
    if not has_matching_chunk:
        return f"No information found for '{name}'. This entity is not in the knowledge base.", []

    # Filter to only keep chunks that belong to the queried entity
    merged = [
        r for r in merged
        if _entity_matches(r.get("metadata", {}).get("entity", ""), name)
    ]

    lines = [f"Information about {name}:\n"]
    for chunk in merged:
        doc = chunk.get("document", "")
        lines.append(doc)
        lines.append("---")

    return "\n".join(lines), merged


def _semantic(col, text: str, where) -> list[dict[str, Any]]:
    try:
        query_emb = embed_single(text)
        return semantic_search(col, query_embedding=query_emb, top_k=TOP_K, where=where)
    except Exception:
        logger.warning("Semantic search failed for '%s'", text)
        return []


def _keyword(col, text: str, where) -> list[dict[str, Any]]:
    return keyword_search(col, query=text, top_k=TOP_K, where=where)


def get_info_person(name: str, query: str | None = None) -> tuple[str, list[dict[str, Any]]]:
    return _retrieve(people_collection, name, query)


def get_info_place(name: str, query: str | None = None) -> tuple[str, list[dict[str, Any]]]:
    return _retrieve(places_collection, name, query)


# ---------------------------------------------------------------------------
# Unified executor (used by ollama_client tool_executor callback)
# ---------------------------------------------------------------------------

async def execute_tool(fn_name: str, fn_args: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Route a tool call to the appropriate retrieval function."""
    name = fn_args.get("name", "")
    query = fn_args.get("query")

    if fn_name == "get_info_person":
        return get_info_person(name, query)
    elif fn_name == "get_info_place":
        return get_info_place(name, query)
    else:
        return f"Unknown tool: {fn_name}", []
