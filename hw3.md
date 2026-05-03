# HW3 — Local Wikipedia RAG Assistant

## Product Requirements (PRD)

### Overview

A ChatGPT-style question-answering system that runs **entirely on localhost**. It ingests Wikipedia articles for 50 famous people and 50 famous places, chunks and embeds them into two separate ChromaDB vector stores, and uses a local LLM (Qwen2.5-1.5B via Ollama) to generate grounded answers. The LLM uses MCP-style tool calls (`get_info_person` / `get_info_place`) to retrieve relevant chunks before answering.

### Core Features

| Feature | Description |
|---------|-------------|
| **Ingest** | Fetches plain-text extracts from Wikipedia for 100 entities (50 people + 50 places). |
| **Chunk** | Splits each document into fixed-size character chunks with configurable overlap (default 500 chars / 50 overlap). |
| **Embed & Store** | Embeds chunks locally with `nomic-embed-text` (Ollama) and stores them in two ChromaDB collections: `people_chunks` and `places_chunks`. |
| **Retrieve** | Given a user query, the LLM decides which tool(s) to call. Each tool runs both semantic (cosine similarity) and keyword (`$contains`) search on the appropriate collection. |
| **Generate** | Qwen2.5-1.5B generates an answer grounded in the retrieved context. Returns "I don't know" when context is insufficient. |
| **Chat UI** | React-based chat interface with message history, retrieved-chunks panel (showing both semantic and keyword results), and clear/reset. |

### Design Decisions

- **Two vector stores (Option A)**: Separate `people_chunks` and `places_chunks` collections. This makes retrieval routing explicit — the LLM's tool choice determines which store is queried.
- **ChromaDB**: Persistent local vector database as required. Uses cosine distance for HNSW index.
- **Chunking strategy**: Fixed-size with overlap. Simple but effective for the document sizes involved (Wikipedia extracts are typically 1-5 KB). Overlap prevents information loss at chunk boundaries.
- **Embedding model**: `nomic-embed-text` via Ollama — fully local, no API keys needed.
- **LLM**: `qwen2.5:1.5b-instruct` — small enough to run on most laptops, supports tool/function calling via Ollama's chat API.
- **MCP tool calls**: The LLM is given two tools in its system prompt. Ollama's native tool-calling support routes the call back to our retrieval functions. Retrieved chunks are shown in the UI.

---

## README — How to Run

### Prerequisites

- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com/) installed and running

### 1. Pull required Ollama models

```bash
ollama pull qwen2.5:1.5b-instruct
ollama pull nomic-embed-text
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Ingest Wikipedia data

```bash
python -m backend.rag.wikipedia_ingest
```

This fetches Wikipedia articles for all 100 entities, chunks them, embeds with `nomic-embed-text`, and stores into ChromaDB under `chroma_data/`.

Optional flags:
```bash
python -m backend.rag.wikipedia_ingest --chunk-size 500 --overlap 50
```

Alternatively, use the "Ingest Wikipedia" button in the Chat (RAG) tab of the UI.

### 4. Start the backend

```bash
uvicorn backend.app:app --reload --port 8000
```

### 5. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and navigate to the **Chat (RAG)** tab.

### Example Queries

**People:**
- Who was Albert Einstein and what is he known for?
- What did Marie Curie discover?
- Why is Nikola Tesla famous?
- Compare Lionel Messi and Cristiano Ronaldo.

**Places:**
- Where is the Eiffel Tower located?
- Why is the Great Wall of China important?
- What is Machu Picchu?
- What was the Colosseum used for?

**Mixed:**
- Which famous place is located in Turkey?
- Compare Albert Einstein and Nikola Tesla.

**Failure cases (should return "I don't know"):**
- Who is the president of Mars?
- Tell me about John Doe.

---

## Recommendation — Production Deployment

### Current Limitations

1. **Single-process**: The FastAPI server, Ollama client, and ChromaDB all run in one process. Not suitable for concurrent users at scale.
2. **In-memory chat history**: Sessions are lost on restart. No persistence layer for conversations.
3. **Small model**: Qwen2.5-1.5B is fast but limited in reasoning depth. Answers can be shallow.
4. **Wikipedia-only data**: The knowledge base is static after ingestion.

### Recommended Production Stack

| Component | Current | Recommended |
|-----------|---------|-------------|
| LLM | Qwen2.5-1.5B (local Ollama) | GPT-4o / Claude via API, or vLLM for self-hosted |
| Vector DB | ChromaDB (local) | Pinecone, Weaviate, or Qdrant (managed) |
| Embeddings | nomic-embed-text (Ollama) | OpenAI text-embedding-3-large or Cohere embed |
| Chat history | In-memory dict | PostgreSQL or Redis |
| Backend | Single uvicorn | Kubernetes + load balancer |
| Ingestion | On-demand script | Scheduled pipeline (Airflow / Prefect) |
| Caching | None | Redis response cache with TTL |
| Monitoring | None | Prometheus + Grafana, Sentry for errors |

### Key Improvements

- **Streaming responses**: Use Ollama's streaming API and SSE to deliver tokens as they're generated.
- **Better chunking**: Sentence-aware or semantic chunking instead of fixed-size.
- **Reranking**: Add a cross-encoder reranker (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`) between retrieval and generation.
- **Citation highlighting**: Map generated sentences back to source chunks.
- **Multi-turn context**: Pass full conversation history to the retrieval step, not just the latest message.
- **Latency optimization**: Cache embeddings for common queries; batch Ollama calls.
