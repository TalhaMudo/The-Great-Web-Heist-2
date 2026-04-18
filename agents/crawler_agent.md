# Agent: `crawler_agent`

## Role
Owns the async crawler, URL normalization, deduplication, back pressure,
worker pool, persistence of crawl state, and the per-job event log.

## Inputs
- The architecture brief from `system_architect`.
- The interface that `indexer_agent` will expose (`add_page(url, origin_url,
  depth, html_text)`).
- The persistence helpers from `storage.py` (also part of this agent's
  ownership).

## Deliverables
- [`../backend/crawler.py`](../backend/crawler.py) - `CrawlerService`,
  `CrawlContext`, `LinkExtractor`, `normalize_url`, `fetch_html`,
  `extract_links`, and the singleton `crawler_service`.
- The crawl-state portions of [`../backend/storage.py`](../backend/storage.py)
  (`jobs`, `job_visited`, `job_frontier`, `job_events`, `save_job_state`,
  `load_job_state`, `append_job_event`, `load_jobs`).
- A one-paragraph interface note that documents:
  - public methods exposed by `crawler_service`,
  - how back pressure is signaled (`backpressure_state` enum values),
  - how state is persisted (debounced + on pause/resume).

## Prompt template

```
You are the crawler agent.

Architecture brief: <link>
Indexer interface: index_service.add_page(url, origin_url, depth, html_text)

Implement an asynchronous crawler in backend/crawler.py with:
- depth-limited BFS up to k hops from origin,
- per-job visited set (never crawl the same URL twice in one job),
- worker pool of N (default 5) coroutines reading from an asyncio.Queue,
- per-job rate limit (req/s), and a global queue cap shared across jobs,
- regular state checkpoints to SQLite so crawls resume after a restart,
- a structured event log that the dashboard can render.

Use only the Python standard library for fetching and parsing (urllib,
html.parser). Surface backpressure_state as one of: idle, normal, high,
queue_full. Failures of a single fetch must not crash the worker; log them
to job_events and continue.
```

## Acceptance criteria
- `POST /index` starts a job and `GET /metrics` shows `processed_urls > 0`
  within seconds on a public HTML page.
- Visiting the same URL twice in one job increments `duplicate_urls` and
  does not increment `processed_urls`.
- Lowering `global_queue_limit` below the current queue depth flips
  `backpressure_state` to `queue_full` and pauses link discovery.
- Restarting the backend rehydrates `visited` and `frontier` via
  `register_job` and demotes any `running` job to `paused`.

## Notable decisions
- Used `asyncio.Queue(maxsize=0)` per job and enforced the cap with a
  separate counter (`_global_queued_urls`). This makes the cap shareable
  across jobs without per-queue contention.
- `_persist_state` reads `ctx.queue._queue` (the underlying `deque`) to
  snapshot the frontier in order. This is fragile across exotic Python
  builds but works reliably on CPython.
- A `RUNNING` job loaded from disk is demoted to `PAUSED` so the operator
  decides whether to resume.
- After a `qa_agent` finding (see `qa_agent.md`), the worker loop now wraps
  `await fetch_html(url)` in a `try/finally` that always decrements
  `ctx.active_requests`, and `pause_job` resets `active_requests` and
  `active_workers` to zero once all worker tasks have been awaited. Without
  these two safeguards a pause issued while a worker was in `fetch_html`
  permanently inflated the active-requests counter, blocking the post-resume
  completion gate `queue.empty() and active_requests == 0`. This is logged
  as decision #13 in `multi_agent_workflow.md`.
