# Product Requirements Document -- The Great Web Heist

This PRD describes the full system across all three homework assignments. It is written for an AI coding agent (or a human developer) to understand, extend, or rebuild the system.

## 1. Problem Statement

We need a system that:

1. **Crawls and indexes** web pages from any origin URL up to depth `k`, exposing search over crawled data (HW1).
2. Uses a **documented multi-agent AI workflow** for the development process (HW2).
3. **Ingests Wikipedia data** for famous people and places, chunks and embeds it locally, and uses a **local LLM with MCP tool calls** to answer questions in a chat interface -- a simplified retrieval-augmented generation (RAG) system (HW3).

The entire system must run on localhost. No external LLM or embedding APIs are allowed.

## 2. Goals

| ID  | Goal | HW |
| --- | ---- | -- |
| G1  | `index(origin, k)` performs a depth-limited, deduplicated crawl on a single machine. | 1 |
| G2  | `search(query)` returns triples `(relevant_url, origin_url, depth)`; results update live during active crawls. | 1 |
| G3  | The system enforces back pressure via a global queue cap and per-job request rate limit. | 1 |
| G4  | A React dashboard and a Python CLI let a user start indexing, search, and inspect runtime state. | 1 |
| G5  | Crawl state and indexed pages persist to SQLite so search works after restart and crawls can resume. | 1 |
| G6  | Optional semantic search using `all-MiniLM-L6-v2` embeddings on crawled pages. | 1 |
| G7  | Development uses a documented multi-agent workflow (system architect, crawler agent, search agent, UI agent, etc.). | 2 |
| G8  | Ingest at least 20 famous people and 20 famous places from Wikipedia, chunk, and embed them locally. | 3 |
| G9  | Store embeddings in ChromaDB with two separate vector stores (people and places). | 3 |
| G10 | Retrieve relevant chunks given a user query, routing to the correct store based on the query. | 3 |
| G11 | Generate grounded answers using a local LLM (Qwen2.5-1.5B via Ollama) with MCP tool calls. | 3 |
| G12 | Provide a chat-style UI with message history, retrieved-chunk display, and session management. | 3 |

## 3. Non-Goals

- Internet-scale, multi-machine crawling.
- Production-grade ranking quality (BM25, learning-to-rank).
- Full politeness policies (robots.txt, per-domain budgets).
- Authentication, multi-tenant, or multi-user features.
- External LLM or embedding API calls.
- Streaming responses (optional extension, not required).

## 4. User Stories

### Crawler (HW1/HW2)

- _As a user_, I enter a seed URL and depth `k` in the dashboard and start an indexing job. I see queue depth, processed URL counts, and back pressure state update in near real time.
- _As a user_, I search while the crawl is still running and see results grow as new pages are indexed.
- _As a user_, I can stop the backend, restart it, and immediately search pages indexed in earlier runs.

### RAG Chat (HW3)

- _As a user_, I click "Ingest Wikipedia" in the Chat tab and see 100 entities being fetched, chunked, and embedded.
- _As a user_, I ask "Who was Nikola Tesla?" and the system retrieves relevant chunks from the people vector store and generates a grounded answer.
- _As a user_, I ask "What is the Colosseum?" and the system retrieves from the places vector store.
- _As a user_, I ask "Compare Albert Einstein and Nikola Tesla" and the system calls the person tool for both.
- _As a user_, I ask "Who is the president of Mars?" and the system responds with "I don't know" because no relevant context exists.
- _As a user_, I can view the retrieved chunks (semantic and keyword) that the model used to generate its answer.
- _As a user_, I can switch between multiple chat sessions and see my conversation history.

## 5. Functional Requirements

### 5.1 Web Crawler and Search (HW1)

- `POST /index` accepts `{ origin, k, max_urls_to_visit, rate_limit_per_sec }` and spawns an async crawl job.
- The crawler normalizes URLs, deduplicates, uses a fixed worker pool with `asyncio.Queue`, and enforces back pressure via a global queue cap.
- `GET /search?query=...` returns triples `(relevant_url, origin_url, depth)` from an in-memory TF-IDF index.
- `GET /search/semantic?query=...` returns the same shape using MiniLM cosine similarity.
- SQLite persists pages, jobs, visited sets, and frontier for resumability.

### 5.2 Multi-Agent Workflow (HW2)

- Development documented across agent roles: system_architect, crawler_agent, indexer_agent, semantic_agent, api_agent, ui_agent, qa_agent, doc_agent.
- See `multi_agent_workflow.md` and `agents/*.md`.

### 5.3 Wikipedia Ingestion (HW3)

- Fetch full Wikipedia articles for 50 people and 50 places via the MediaWiki action API.
- Split documents into fixed-size chunks (500 characters, 50 character overlap).
- Embed chunks locally using `nomic-embed-text` via Ollama.
- Store in two ChromaDB collections: `people_chunks` and `places_chunks` (Option A).
- Skip already-ingested entities on re-run; re-ingest entities with too few chunks.
- Rate-limit Wikipedia requests with retry + exponential backoff on 429.

### 5.4 Retrieval (HW3)

- Two MCP tools: `get_info_person(name, query)` and `get_info_place(name, query)`.
- Each tool runs both semantic search (cosine similarity via embedding) and keyword search (`$contains`) on its ChromaDB collection.
- Falls back to unfiltered search if exact entity match returns no results.
- Returns top-5 chunks from each search type, deduplicated.

### 5.5 Generation (HW3)

- Local LLM: `qwen2.5:1.5b-instruct` via Ollama's Python library.
- System prompt mandates tool calls before every answer; the model never answers from its own knowledge.
- Tool-call loop: up to 3 rounds of tool calls before forcing a final answer.
- Responds "I don't know" when retrieved context is insufficient.

### 5.6 Chat Interface (HW3)

- React chat UI in the "Chat (RAG)" tab with:
  - Message history (user + assistant bubbles).
  - Collapsible "Retrieved Chunks" panel after each assistant response, split into semantic and keyword columns.
  - Tool call badges showing which tools were invoked.
  - Session sidebar listing all conversations, with new/switch/delete.
  - Entity ingestion status panel showing all 100 entities with chunk counts.
  - "Ingest Wikipedia" button.

### 5.7 UI Tabs (all HWs)

- **Crawler**: Index control, system metrics, per-job cards, job detail with frontier and events.
- **Search**: Side-by-side lexical and semantic results with triples display.
- **Embeddings**: Control panel for the MiniLM embedding engine on crawled pages.
- **Chat (RAG)**: Session sidebar + chat + chunk display + entity status.

## 6. Technical Constraints

- Backend in Python 3.10+. Core crawler/indexer uses stdlib (`urllib`, `html.parser`, `asyncio`, `sqlite3`).
- Third-party: FastAPI, uvicorn, sentence-transformers, chromadb, ollama, httpx.
- Frontend in TypeScript with React + Vite.
- Local models only: `qwen2.5:1.5b-instruct` (LLM), `nomic-embed-text` (embeddings), `all-MiniLM-L6-v2` (crawled page embeddings).
- Vector store: ChromaDB (persistent, local).
- Database: SQLite for crawler data.
- Single process, single machine.

## 7. Acceptance Criteria

- Crawling a public website yields growing page counts and live search results.
- Back pressure activates when queue limit is exceeded.
- Backend restart preserves crawled data and search functionality.
- Wikipedia ingestion produces chunks in both ChromaDB collections for all 100 entities.
- Asking about a known person/place returns a grounded answer with visible retrieved chunks.
- Asking about an unknown entity returns "I don't know."
- Chat history persists across messages within a session.
- Multiple sessions can be created, switched, and deleted.
