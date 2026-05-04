"""Async Ollama chat client for Qwen2.5-1.5B-Instruct with MCP tool-call
loop and per-session conversation history.

Uses the ``ollama`` Python library (same approach as the reference
``ollama_mcp_client.py``)."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

import ollama as _ollama

logger = logging.getLogger(__name__)

CHAT_MODEL = "qwen2.5:1.5b-instruct"

SYSTEM_PROMPT = """\
You are a RAG assistant. You answer questions ONLY using information retrieved from the knowledge base tools.

MANDATORY RULES:
1. You MUST call at least one tool (get_info_person or get_info_place) for EVERY question. NEVER answer without calling a tool first.
2. If the question mentions a person, call get_info_person. If it mentions a place, call get_info_place. If both, call both.
3. If you are unsure whether the query is about a person or a place, call BOTH tools.
4. After receiving the tool results, answer ONLY based on what the tool returned. Do NOT add any information from your own knowledge.
5. If the tool returns "No information found", respond with: "I don't have information about that in my knowledge base."
6. NEVER skip the tool call. NEVER answer from memory. Every answer must come from the tools.
"""

TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_info_person",
            "description": "Retrieve information chunks about a famous person from the knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the person to look up.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Additional context or question about this person to refine the search.",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_info_place",
            "description": "Retrieve information chunks about a famous place from the knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the place to look up.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Additional context or question about this place to refine the search.",
                    },
                },
                "required": ["name"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Session store (in-memory, with metadata)
# ---------------------------------------------------------------------------

@dataclass
class SessionMeta:
    title: str
    created_at: str
    updated_at: str


_sessions: dict[str, list[dict[str, Any]]] = {}
_session_meta: dict[str, SessionMeta] = {}


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def get_or_create_session(session_id: str | None = None) -> tuple[str, list[dict[str, Any]]]:
    if session_id and session_id in _sessions:
        _session_meta[session_id].updated_at = _now_iso()
        return session_id, _sessions[session_id]
    sid = session_id or str(uuid.uuid4())
    _sessions[sid] = [{"role": "system", "content": SYSTEM_PROMPT}]
    _session_meta[sid] = SessionMeta(
        title="New conversation",
        created_at=_now_iso(),
        updated_at=_now_iso(),
    )
    return sid, _sessions[sid]


def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
    _session_meta.pop(session_id, None)


def list_sessions() -> list[dict[str, Any]]:
    """Return all sessions sorted by most recently updated."""
    out: list[dict[str, Any]] = []
    for sid, meta in _session_meta.items():
        msgs = _sessions.get(sid, [])
        msg_count = sum(1 for m in msgs if m.get("role") in ("user", "assistant"))
        out.append({
            "session_id": sid,
            "title": meta.title,
            "created_at": meta.created_at,
            "updated_at": meta.updated_at,
            "message_count": msg_count,
        })
    out.sort(key=lambda s: s["updated_at"], reverse=True)
    return out


def get_session_history(session_id: str) -> list[dict[str, Any]] | None:
    msgs = _sessions.get(session_id)
    if msgs is None:
        return None
    return [m for m in msgs if m.get("role") in ("user", "assistant")]


def update_session_title(session_id: str, title: str) -> None:
    if session_id in _session_meta:
        _session_meta[session_id].title = title


# ---------------------------------------------------------------------------
# Helpers to normalise the ollama library's Message objects to dicts
# ---------------------------------------------------------------------------

def _msg_to_dict(msg: Any) -> dict[str, Any]:
    """Convert an ollama Message (or already-a-dict) to a plain dict."""
    if isinstance(msg, dict):
        return msg
    if hasattr(msg, "model_dump"):
        return msg.model_dump()
    return {"role": str(getattr(msg, "role", "assistant")),
            "content": str(getattr(msg, "content", ""))}


def _extract_tool_calls(msg: Any) -> list[dict[str, Any]]:
    """Pull tool_calls from an ollama Message, normalise to list[dict]."""
    raw = msg.get("tool_calls") if isinstance(msg, dict) else getattr(msg, "tool_calls", None)
    if not raw:
        return []
    out: list[dict[str, Any]] = []
    for tc in raw:
        if isinstance(tc, dict):
            out.append(tc)
        else:
            fn = getattr(tc, "function", None)
            if fn is None:
                continue
            out.append({
                "function": {
                    "name": getattr(fn, "name", ""),
                    "arguments": getattr(fn, "arguments", {}),
                }
            })
    return out


# ---------------------------------------------------------------------------
# Synchronous Ollama call (run in executor for async FastAPI)
# ---------------------------------------------------------------------------

def _chat_sync(messages: list[dict[str, Any]]) -> Any:
    """Blocking call to ollama.chat() -- mirrors the reference client."""
    return _ollama.chat(
        model=CHAT_MODEL,
        messages=messages,
        tools=TOOLS_SCHEMA,
    )


# ---------------------------------------------------------------------------
# Core chat loop
# ---------------------------------------------------------------------------

async def chat(
    user_message: str,
    session_id: str | None = None,
    tool_executor=None,
    max_tool_rounds: int = 3,
) -> dict[str, Any]:
    """Send *user_message* through Ollama with a tool-call loop.

    ``tool_executor`` is an async callable ``(name, args) -> (str, list)``
    that invokes the appropriate MCP tool and returns textual result + chunks.
    """
    sid, history = get_or_create_session(session_id)
    history.append({"role": "user", "content": user_message})

    # Auto-title from first user message
    user_msgs = [m for m in history if m.get("role") == "user"]
    if len(user_msgs) == 1 and sid in _session_meta:
        _session_meta[sid].title = user_message[:60] + ("..." if len(user_message) > 60 else "")

    all_tool_calls: list[dict[str, Any]] = []
    all_chunks: list[dict[str, Any]] = []
    loop = asyncio.get_running_loop()

    for _round in range(max_tool_rounds + 1):
        response = await loop.run_in_executor(None, _chat_sync, list(history))

        # response is a ChatResponse; response["message"] is a Message object
        assistant_message = response["message"]
        tool_calls = _extract_tool_calls(assistant_message)

        if not tool_calls:
            content = assistant_message.get("content") if isinstance(assistant_message, dict) else getattr(assistant_message, "content", "")
            answer = content or ""
            history.append({"role": "assistant", "content": answer})
            return {
                "session_id": sid,
                "answer": answer,
                "tool_calls": all_tool_calls,
                "chunks_retrieved": all_chunks,
                "history": [m for m in history if m.get("role") != "system"],
            }

        # Append the raw assistant message (with tool_calls) to history
        history.append(_msg_to_dict(assistant_message))

        for tc in tool_calls:
            fn = tc.get("function", {})
            fn_name = fn.get("name", "")
            fn_args = fn.get("arguments", {})
            if isinstance(fn_args, str):
                try:
                    fn_args = json.loads(fn_args)
                except json.JSONDecodeError:
                    fn_args = {"name": fn_args}

            all_tool_calls.append({"name": fn_name, "arguments": fn_args})

            if tool_executor:
                result_text, chunks = await tool_executor(fn_name, fn_args)
                all_chunks.extend(chunks)
            else:
                result_text = "Tool execution not available."

            history.append({
                "role": "tool",
                "content": result_text,
            })

    answer = "I was unable to produce an answer after multiple tool rounds."
    history.append({"role": "assistant", "content": answer})
    return {
        "session_id": sid,
        "answer": answer,
        "tool_calls": all_tool_calls,
        "chunks_retrieved": all_chunks,
        "history": [m for m in history if m.get("role") != "system"],
    }
