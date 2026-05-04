# The Great Web Heist

A progressive web crawler, search engine, and local RAG assistant built across three homework assignments for **BLG 483E AI Aided Computer Engineering**.

- **HW1**: Depth-limited web crawler with lexical search and back pressure.
- **HW2**: Same system rebuilt using a documented multi-agent AI workflow.
- **HW3**: Local Wikipedia RAG assistant -- ingest, chunk, embed, retrieve, and generate answers using a local LLM with MCP tool calls.

The entire system runs on localhost. No external APIs are used for the LLM or embeddings.

## Repository Layout

```
backend/
  app.py              FastAPI HTTP API (all endpoints)
  crawler.py           Async crawler + back pressure + persistence
  indexer.py           In-memory inverted index (TF-IDF)
  semantic_index.py    MiniLM-based vector search for crawled pages
  storage.py           SQLite persistence layer
  models.py            Dataclasses + types
  cli.py               Command-line interface
  rag/
    entities.py        Hardcoded 50 people + 50 places
    wikipedia_ingest.py  Fetch Wikipedia, chunk, embed, store into ChromaDB
    chroma_store.py    ChromaDB wrapper (people_chunks + places_chunks)
    mcp_server.py      MCP tools: get_info_person / get_info_place
    ollama_client.py   Ollama chat client with tool-call loop + session history
    router.py          FastAPI router for /rag/* endpoints
frontend/
  src/App.tsx          Dashboard (Crawler / Search / Embeddings / Chat tabs)
  src/styles.css
  vite.config.ts       Dev server proxy
agents/                Per-agent prompt + responsibility files (HW2)
multi_agent_workflow.md
product_prd.md
recommendation.md
requirements.txt
```

## Prerequisites

- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com/) installed and running

## How to Run

### 1. Start Ollama and pull models

```bash
ollama serve
```

In a separate terminal, pull the required models:

```bash
ollama pull qwen2.5:1.5b-instruct
ollama pull nomic-embed-text
```

Verify they are available:

```bash
ollama list
```

### 2. Install Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Start the backend

```bash
uvicorn backend.app:app --reload --port 8000
```

The backend listens on `http://127.0.0.1:8000`. SQLite database `crawler.db` is created next to the `backend/` package on first run. ChromaDB data is stored in `chroma_data/`.

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The Vite dev server proxies all API calls to the backend.

### 5. Ingest Wikipedia data (for HW3 RAG)

Either use the **"Ingest Wikipedia"** button in the Chat (RAG) tab, or run from the command line:

```bash
python -m backend.rag.wikipedia_ingest
```

This fetches Wikipedia articles for 100 entities (50 people + 50 places), splits them into chunks (500 chars with 50 overlap), embeds them with `nomic-embed-text`, and stores them into two ChromaDB collections.

### 6. CLI (no UI required)

```bash
# Crawl a site
python -m backend.cli index https://en.wikipedia.org/wiki/Web_crawler 1 --max-urls 50 --rate 2

# Lexical search
python -m backend.cli search "search engine" --limit 10

# Check job status
python -m backend.cli status
```

## Features by Homework

### HW1 -- Web Crawler and Search

- `POST /index` starts an async, depth-limited crawl with back pressure and per-job rate limiting.
- `GET /search?query=...` returns triples `(relevant_url, origin_url, depth)` from a live in-memory TF-IDF index.
- `GET /search/semantic?query=...` returns the same shape using MiniLM cosine similarity.
- SQLite persistence rebuilds the index on restart; paused jobs can be resumed.
- Back pressure via global queue cap and per-job throttling.

### HW2 -- Multi-Agent Workflow

The HW1 system was rebuilt using a documented multi-agent AI workflow. See [`multi_agent_workflow.md`](./multi_agent_workflow.md) and [`agents/`](./agents) for the agent roles, prompts, and hand-offs.

### HW3 -- Local Wikipedia RAG Assistant

- **Ingest**: Fetches full Wikipedia articles for 50 famous people and 50 famous places via the MediaWiki API.
- **Chunk**: Fixed-size character chunking (500 chars, 50 overlap) with retry and rate-limit handling.
- **Embed & Store**: Embeds chunks locally with `nomic-embed-text` (Ollama) into two ChromaDB collections: `people_chunks` and `places_chunks` (Option A -- two vector stores).
- **Retrieve**: The LLM calls MCP tools (`get_info_person` / `get_info_place`) which run both semantic (cosine similarity) and keyword (`$contains`) search on the appropriate collection.
- **Generate**: `qwen2.5:1.5b-instruct` via Ollama generates answers grounded in retrieved context. Returns "I don't know" when context is insufficient.
- **Chat UI**: React chat interface with message history, session sidebar, retrieved-chunks panel (semantic + keyword results side by side), and session management.
- **Chat history**: In-memory per-session conversation history with session listing and switching.

#### Design Choices

- **Two vector stores (Option A)**: Separate `people_chunks` and `places_chunks` collections. The LLM's tool choice determines which store is queried, making retrieval routing explicit.
- **ChromaDB**: Persistent local vector database with cosine distance HNSW index.
- **Chunking**: Fixed-size with overlap. Simple but effective for Wikipedia article sizes. Overlap prevents information loss at chunk boundaries.
- **Embedding model**: `nomic-embed-text` via Ollama (768-dimensional, fully local).
- **LLM**: `qwen2.5:1.5b-instruct` -- small enough for any laptop, supports Ollama's native tool/function calling.
- **Mandatory tool calls**: System prompt forces the model to always call retrieval tools before answering, ensuring all responses are grounded in the knowledge base.

## Example Queries (HW3)

**People:**
- Who was Albert Einstein and what is he known for?
- What did Marie Curie discover?
- Why is Nikola Tesla famous?
- Compare Lionel Messi and Cristiano Ronaldo.
- What is Frida Kahlo known for?

**Places:**
- Where is the Eiffel Tower located?
- Why is the Great Wall of China important?
- What is Machu Picchu?
- What was the Colosseum used for?
- Where is Mount Everest?

**Mixed:**
- Which famous place is located in Turkey?
- Which person is associated with electricity?
- Compare Albert Einstein and Nikola Tesla.
- Compare the Eiffel Tower and the Statue of Liberty.

**Failure cases (should return "I don't know"):**
- Who is the president of Mars?
- Tell me about a random unknown person John Doe.

## API Reference

### Crawling (HW1/HW2)

- `POST /index` -- start a crawl job
- `GET /search?query=...` -- lexical search
- `GET /search/semantic?query=...` -- semantic search
- `GET /metrics` -- system-wide counters
- `GET /jobs/{id}` -- per-job detail
- `POST /jobs/{id}/pause` / `POST /jobs/{id}/resume`

### RAG Chat (HW3)

- `POST /rag/chat` -- send a message, get an answer with tool calls and retrieved chunks
- `GET /rag/sessions` -- list all chat sessions
- `GET /rag/sessions/{id}` -- load a session's history
- `POST /rag/chat/clear?session_id=...` -- delete a session
- `POST /rag/ingest` -- ingest all Wikipedia entities
- `GET /rag/status` -- chunk counts and per-entity ingestion status
- `GET /rag/entities` -- list all hardcoded people and places

## Limitations

- Single-process; not designed for concurrent users at scale.
- No `robots.txt` enforcement for the general crawler.
- Chat history is in-memory (lost on backend restart).
- Qwen2.5-1.5B is fast but limited in reasoning depth; answers can be shallow.
- Wikipedia data is static after ingestion.
