# Agent: `semantic_agent`

## Role
Owns the optional semantic search engine: model loading, the embedding
worker, the in-memory vector cache, and the SQLite-backed vector store.

## Inputs
- The architecture brief from `system_architect`.
- The lexical index API (used so we can show both result panels in the UI).
- The persistence helpers `save_page_embedding`, `load_page_embeddings`,
  `load_embedding_targets`, `count_pages`, `count_page_embeddings`.

## Deliverables
- [`../backend/semantic_index.py`](../backend/semantic_index.py) -
  `SemanticIndexService` and the `semantic_index_service` singleton.
- The `page_embeddings` table in
  [`../backend/storage.py`](../backend/storage.py).

## Prompt template

```
You are the semantic search agent.

Architecture brief: <link>
Constraint: model is sentence-transformers all-MiniLM-L6-v2; load lazily on
the first start_engine() call. Crawl + lexical search must keep working
even if sentence-transformers is not installed.

Implement backend/semantic_index.py with:
- start_engine(rate_limit_per_sec, max_pages) launches a single asyncio
  task that pulls un-embedded pages from SQLite, embeds them, and persists
  the vector,
- pause_engine() cancels the task without losing already-stored vectors,
- update_rate_limit() and clear_embeddings() do exactly what they say,
- search(query, limit) returns the same shape the lexical engine returns,
  so the UI can render both side by side,
- get_engine_status() returns a dataclass the API can render as JSON.
```

## Acceptance criteria
- `POST /embeddings/start` followed by polling `GET /embeddings/status`
  shows `embedded_pages` rising at roughly `rate_limit_per_sec` pages/sec.
- `POST /embeddings/pause` halts work; `start` resumes it without
  re-embedding pages that already have a vector.
- `POST /embeddings/clear` deletes everything from `page_embeddings` and
  resets the in-memory cache.
- `GET /search/semantic?query=...` returns a list of triples once at least
  a few pages have been embedded.

## Notable decisions
- The model is loaded inside `_get_or_load_model_sync` and cached, so the
  first call pays the cost and subsequent encodings are fast.
- Vectors are stored as JSON strings in SQLite. This is not optimal but it
  keeps the persistence layer dependency-free; production would use a real
  vector store (recommendation.md).
- The engine runs as a single coroutine, not a worker pool: encoding is
  CPU-bound and we want to leave the event loop responsive for the
  crawler.
