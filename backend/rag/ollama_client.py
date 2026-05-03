"""Async Ollama chat client for Qwen2.5-1.5B-Instruct with MCP tool-call
loop and per-session conversation history.

Uses the ``ollama`` Python library (same approach as the reference
``ollama_mcp_client.py``)."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import ollama as _ollama

logger = logging.getLogger(__name__)

CHAT_MODEL = "qwen2.5:1.5b-instruct"

SYSTEM_PROMPT = """\
You are a helpful assistant that answers questions about famous people and places.
You MUST use the provided tools to look up information before answering.
- Use get_info_person when the question involves a person.
- Use get_info_place when the question involves a place.
- If the question involves both a person and a place, call both tools.
- If the retrieved context does not contain enough information, say "I don't know based on the available data."
- Always ground your answer in the retrieved context. Do not make up facts.
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
# Session store (in-memory)
# ---------------------------------------------------------------------------

_sessions: dict[str, list[dict[str, Any]]] = {}


def get_or_create_session(session_id: str | None = None) -> tuple[str, list[dict[str, Any]]]:
    if session_id and session_id in _sessions:
        return session_id, _sessions[session_id]
    sid = session_id or str(uuid.uuid4())
    _sessions[sid] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return sid, _sessions[sid]


def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


# ---------------------------------------------------------------------------
# Synchronous Ollama call (run in executor for async FastAPI)
# ---------------------------------------------------------------------------

def _chat_sync(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Blocking call to ollama.chat() -- mirrors the reference client."""
    response = _ollama.chat(
        model=CHAT_MODEL,
        messages=messages,
        tools=TOOLS_SCHEMA,
    )
    return response


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

    all_tool_calls: list[dict[str, Any]] = []
    all_chunks: list[dict[str, Any]] = []
    loop = asyncio.get_running_loop()

    for _round in range(max_tool_rounds + 1):
        response = await loop.run_in_executor(None, _chat_sync, list(history))

        assistant_message = response.get("message") or response
        if isinstance(assistant_message, dict):
            pass
        else:
            assistant_message = {"role": "assistant", "content": str(assistant_message)}

        tool_calls = assistant_message.get("tool_calls") or []

        if not tool_calls:
            answer = assistant_message.get("content", "")
            history.append({"role": "assistant", "content": answer})
            return {
                "session_id": sid,
                "answer": answer,
                "tool_calls": all_tool_calls,
                "chunks_retrieved": all_chunks,
                "history": [m for m in history if m["role"] != "system"],
            }

        history.append(assistant_message)

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
        "history": [m for m in history if m["role"] != "system"],
    }
