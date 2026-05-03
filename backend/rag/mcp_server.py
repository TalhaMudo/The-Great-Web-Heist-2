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

def _retrieve(
    collection_getter,
    name: str,
    query: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Run semantic + keyword search on a collection and return a
    formatted text block plus the raw chunk list for the UI."""

    col = collection_getter()
    search_text = f"{name} {query}" if query else name

    # Semantic search
    try:
        query_emb = embed_single(search_text)
        sem_results = semantic_search(
            col, query_embedding=query_emb, top_k=TOP_K,
            where={"entity": name} if name else None,
        )
    except Exception:
        logger.warning("Semantic search failed for %s, falling back to keyword only", name)
        sem_results = []

    # Keyword search
    kw_results = keyword_search(
        col, query=search_text, top_k=TOP_K,
        where={"entity": name} if name else None,
    )

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

    lines = [f"Information about {name}:\n"]
    for chunk in merged:
        doc = chunk.get("document", "")
        lines.append(doc)
        lines.append("---")

    return "\n".join(lines), merged


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
