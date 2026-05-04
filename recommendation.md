# Production Deployment Recommendation

This document covers what it would take to deploy the full system (web crawler + search + RAG assistant) into a production environment, including the tradeoffs made in the current implementation and what should change.

## Current Architecture (Localhost Prototype)

| Component | Technology | Limitation |
|-----------|-----------|------------|
| Backend | Single FastAPI process | No horizontal scaling |
| Crawler | asyncio worker pool + in-process queue | Single-machine, no distributed coordination |
| Lexical search | In-memory TF-IDF inverted index | Lost on restart, rebuilt from SQLite |
| Semantic search (crawled pages) | MiniLM + in-memory vectors | Slow on large corpora, no ANN index |
| RAG vector store | ChromaDB (local persistent) | Single-node, no replication |
| RAG embeddings | nomic-embed-text via Ollama | Local-only, slower than API embeddings |
| LLM | Qwen2.5-1.5B via Ollama | Small model, limited reasoning depth |
| Chat history | In-memory Python dict | Lost on restart |
| Database | SQLite (WAL mode) | Single-writer, no concurrent access from multiple processes |
| Frontend | React SPA polling every 2-3s | No WebSocket push |

## Recommended Production Stack

### Crawler and Search (HW1/HW2 components)

The crawler should become a horizontally scalable worker pool pulling jobs from a durable message broker (Kafka, RabbitMQ, or a managed cloud queue) instead of an in-process asyncio.Queue. Back pressure should move from a process-local counter to broker-enforced concurrency caps plus per-domain token buckets, enabling robots.txt compliance and per-domain crawl budgets.

Page storage should move from SQLite to PostgreSQL for metadata and crawl-state tables, with S3 or equivalent for raw HTML snapshots. The lexical index should move to Elasticsearch or OpenSearch (with BM25), and the semantic vectors for crawled pages should move to a purpose-built vector store (pgvector, Qdrant, or Weaviate). The search API then becomes a stateless service that fans queries to both engines, scaling independently from the crawl fleet.

### RAG System (HW3 components)

| Component | Current | Recommended |
|-----------|---------|-------------|
| LLM | Qwen2.5-1.5B (Ollama, local) | GPT-4o / Claude API for quality, or vLLM with Llama 3.1 70B for self-hosted |
| Vector DB | ChromaDB (local) | Qdrant, Weaviate, or Pinecone (managed, replicated) |
| Embeddings | nomic-embed-text (Ollama) | OpenAI text-embedding-3-large or Cohere embed-v3 |
| Chat history | In-memory dict | PostgreSQL or Redis with TTL |
| Ingestion | On-demand script / button | Scheduled pipeline (Airflow / Prefect) with incremental updates |
| Chunking | Fixed-size 500 chars | Sentence-aware or semantic chunking for better context preservation |

### Infrastructure

- **Containers + orchestration**: Run all services in Docker containers under Kubernetes (or ECS/Cloud Run) with auto-scaling based on request load.
- **Monitoring**: Structured logs, Prometheus metrics (queue depth, fetch latency, LLM latency, error rate, per-domain QPS), Grafana dashboards, and distributed traces via OpenTelemetry.
- **CI/CD**: Linting, type checks, unit tests for URL normalizer/tokenizer/chunker, integration tests for end-to-end crawl/search/RAG behavior on synthetic data, blocking deploys on regressions.

## Key Improvements for Production RAG

1. **Streaming responses**: Use Ollama's streaming API (or vLLM) with Server-Sent Events to deliver tokens as they are generated, improving perceived latency.

2. **Better chunking**: Replace fixed-size character chunking with sentence-aware chunking (split on sentence boundaries) or semantic chunking (group sentences by topic similarity). This produces more coherent chunks and better retrieval quality.

3. **Reranking**: Add a cross-encoder reranker (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`) between retrieval and generation. Initial retrieval returns top-20 candidates; the reranker scores them against the query and passes top-5 to the LLM.

4. **Citation highlighting**: Map each generated sentence back to its source chunk(s). Display inline citations in the chat UI so users can verify claims against the original Wikipedia text.

5. **Multi-turn retrieval**: Currently only the latest user message drives retrieval. In production, the full conversation context should be summarized or reformulated before querying the vector store, so follow-up questions like "What else did he do?" resolve correctly.

6. **Hybrid search**: Combine dense (embedding) and sparse (BM25) retrieval in a single ranked list using reciprocal rank fusion or a learned combiner, rather than showing them side-by-side.

7. **Caching**: Cache embedding vectors for repeated queries and cache LLM responses for identical (query, context) pairs using Redis with a TTL.

8. **Evaluation**: Add automated evaluation using a held-out QA dataset (e.g., generated from the ingested Wikipedia data) to measure retrieval recall@k, answer correctness, and hallucination rate across model/chunking/retrieval configurations.

## Tradeoffs in the Current Implementation

- **Fixed-size chunking** is simple to implement and reason about, but can split sentences mid-thought. We chose it because Wikipedia articles vary widely in length and the fixed approach handles both short and long documents predictably.

- **Two separate vector stores** (Option A) makes the retrieval routing explicit and avoids metadata filtering overhead, but requires the LLM to correctly classify whether a query is about a person or place. For ambiguous queries, the system calls both tools.

- **Qwen2.5-1.5B** is the smallest model that reliably supports Ollama's tool-calling API. It runs fast on any laptop but produces shorter, less nuanced answers than larger models. A production deployment would use a 7B+ model or an API-based model.

- **In-memory chat history** was chosen for simplicity. A production system would persist sessions to a database and support multi-device access.

- **Wikipedia API ingestion** (instead of using the project's own crawler) was chosen for reliability and speed -- the MediaWiki API returns clean plaintext directly, avoiding HTML parsing edge cases on Wikipedia's complex page templates.
