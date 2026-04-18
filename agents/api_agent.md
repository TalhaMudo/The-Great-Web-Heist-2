# Agent: `api_agent`

## Role
Owns the FastAPI surface: request/response models, endpoint wiring, error
semantics, and the on-startup hook that rebuilds in-memory state.

## Inputs
- The architecture brief from `system_architect`.
- Public interfaces from `crawler_agent`, `indexer_agent`, and
  `semantic_agent`.
- The required response shape: every search result must include the
  assignment-shaped triple `(relevant_url, origin_url, depth)`.

## Deliverables
- [`../backend/app.py`](../backend/app.py) - all FastAPI endpoints, the
  request/response Pydantic models, the search response that exposes both
  `triples` and `results`, the startup hook, and the CORS middleware.

## Prompt template

```
You are the HTTP API agent.

Architecture brief: <link>
Crawler interface: crawler_service.start_job(job, rate_limit_per_sec)
                   crawler_service.pause_job(id) / resume_job(id) /
                   update_job_rate_limit(id, rate) /
                   set_global_queue_limit(n)
Lexical interface: index_service.search(query, limit)
Semantic interface: semantic_index_service.search(query, limit) /
                    start_engine / pause_engine / update_rate_limit /
                    clear_embeddings / get_engine_status

Expose endpoints:
- POST /index, GET /search, GET /search/semantic,
- GET /jobs/{id}, POST /jobs/{id}/pause, POST /jobs/{id}/resume,
  POST /jobs/{id}/rate-limit,
- POST /settings/queue-limit, GET /metrics,
- GET /embeddings/status, POST /embeddings/start, POST /embeddings/pause,
  POST /embeddings/rate-limit, POST /embeddings/clear,
- GET / (health).

The /search and /search/semantic responses MUST contain a "triples" array
exactly matching the assignment contract:
  [{"relevant_url": str, "origin_url": str, "depth": int}, ...]
plus a richer "results" array with score and title for the UI.
```

## Acceptance criteria
- Every endpoint responds with the expected status code and shape on the
  happy path.
- Bad input (negative `k`, non-positive `max_urls_to_visit`, zero-or-less
  rate limits) returns HTTP 400 with a `detail` message.
- The startup hook calls `init_db()`, replays `pages` into the lexical
  index, registers persisted jobs, and initializes the semantic cache.

## Notable decisions
- Returned both `triples` and `results` so the assignment contract is
  visible in the JSON without losing the metadata the UI needs.
- Added `CORSMiddleware(allow_origins=["*"])` so the React dev server can
  call the API directly even when the Vite proxy is bypassed (e.g. when
  running the built frontend from a static host).
