"""FastAPI router for RAG chat endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .chroma_store import collection_count, people_collection, places_collection
from .entities import PEOPLE, PLACES
from .mcp_server import execute_tool
from .ollama_client import chat, clear_session

logger = logging.getLogger(__name__)

rag_router = APIRouter(prefix="/rag", tags=["rag"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChunkInfo(BaseModel):
    id: str
    document: str
    entity: str | None = None
    search_type: str | None = None
    distance: float | None = None


class ToolCallInfo(BaseModel):
    name: str
    arguments: dict[str, Any]


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    tool_calls: list[ToolCallInfo]
    chunks_retrieved: list[ChunkInfo]
    history: list[ChatMessage]


class IngestRequest(BaseModel):
    chunk_size: int = 500
    overlap: int = 50


class IngestResult(BaseModel):
    entity: str
    category: str
    status: str
    chunks: int


class IngestResponse(BaseModel):
    results: list[IngestResult]
    total_ok: int
    total_chunks: int


class EntityListResponse(BaseModel):
    people: list[str]
    places: list[str]


class StatusResponse(BaseModel):
    people_chunks: int
    places_chunks: int
    total_chunks: int
    people_count: int
    places_count: int


class ClearResponse(BaseModel):
    cleared: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@rag_router.post("/chat", response_model=ChatResponse)
async def rag_chat(req: ChatRequest) -> ChatResponse:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    try:
        result = await chat(
            user_message=req.message,
            session_id=req.session_id,
            tool_executor=execute_tool,
        )
    except Exception as exc:
        logger.exception("Chat failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    chunks = [
        ChunkInfo(
            id=c.get("id", ""),
            document=c.get("document", ""),
            entity=c.get("metadata", {}).get("entity"),
            search_type=c.get("search_type"),
            distance=c.get("distance"),
        )
        for c in result.get("chunks_retrieved", [])
    ]
    tool_calls = [
        ToolCallInfo(name=tc["name"], arguments=tc["arguments"])
        for tc in result.get("tool_calls", [])
    ]
    history = [
        ChatMessage(role=m["role"], content=m.get("content", ""))
        for m in result.get("history", [])
    ]
    return ChatResponse(
        session_id=result["session_id"],
        answer=result["answer"],
        tool_calls=tool_calls,
        chunks_retrieved=chunks,
        history=history,
    )


@rag_router.post("/chat/clear", response_model=ClearResponse)
async def rag_clear(session_id: str | None = None) -> ClearResponse:
    if session_id:
        clear_session(session_id)
    return ClearResponse(cleared=True)


@rag_router.get("/entities", response_model=EntityListResponse)
async def rag_entities() -> EntityListResponse:
    return EntityListResponse(people=PEOPLE, places=PLACES)


@rag_router.post("/ingest", response_model=IngestResponse)
async def rag_ingest(req: IngestRequest) -> IngestResponse:
    from .wikipedia_ingest import ingest_all

    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(
        None, lambda: ingest_all(chunk_size=req.chunk_size, overlap=req.overlap)
    )
    ok = sum(1 for r in results if r["status"] == "ok")
    total_chunks = sum(r["chunks"] for r in results)
    return IngestResponse(
        results=[IngestResult(**r) for r in results],
        total_ok=ok,
        total_chunks=total_chunks,
    )


@rag_router.get("/status", response_model=StatusResponse)
async def rag_status() -> StatusResponse:
    pc = collection_count(people_collection())
    lc = collection_count(places_collection())
    return StatusResponse(
        people_chunks=pc,
        places_chunks=lc,
        total_chunks=pc + lc,
        people_count=len(PEOPLE),
        places_count=len(PLACES),
    )
