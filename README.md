# The Great Web Heist 2 - Multi-Agent Crawler

This is the second homework for **BLG 483E AI Aided Computer Engineering**. It
re-implements the same web crawler + search system as Homework 1, but the
build process uses a documented multi-agent AI workflow. The codebase itself
runs in a single FastAPI process (with an optional CLI and a React dashboard);
the multi-agent angle is in **how it was designed and assembled**. See
[`multi_agent_workflow.md`](./multi_agent_workflow.md) and
[`agents/`](./agents) for that story.

## What the system does

- `index(origin, k)`: starts an async, depth-limited crawl from `origin` to
  depth `k`. URLs are normalized and deduplicated per job. A fixed worker pool
  pulls from an `asyncio.Queue` while a global queue cap and per-job rate
  limit keep the system under control (back pressure).
- `search(query)`: returns triples `(relevant_url, origin_url, depth)` from
  the live in-memory index. Search works while a crawl is still in progress;
  newly indexed pages appear automatically. There is also an optional
  `semantic_search` mode using MiniLM embeddings.
- A React dashboard exposes indexing controls, system metrics (queue depth,
  back pressure, workers), per-job state (frontier preview, events), and
  search.
- A small CLI (`python -m backend.cli`) does the same things from a terminal.
- SQLite persistence rebuilds the in-memory index on startup, so search
  continues to work after a restart and paused jobs can be resumed.

## Repository layout

```
backend/
  app.py              FastAPI HTTP API
  crawler.py          Async crawler + back pressure + persistence
  indexer.py          In-memory inverted index (TF-IDF over stdlib tokens)
  semantic_index.py   Optional MiniLM-based vector search
  storage.py          SQLite persistence layer
  models.py           Dataclasses + types (incl. SearchTriple)
  cli.py              Command-line interface
frontend/
  src/App.tsx         Dashboard (Crawler / Search / Embeddings tabs)
  src/styles.css
  vite.config.ts      Dev server proxy: forwards API calls to :8000
agents/               Per-agent prompt + responsibility files
multi_agent_workflow.md
product_prd.md
recommendation.md
requirements.txt
```

## How to run

### Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app:app --reload
```

Backend listens on `http://127.0.0.1:8000`. SQLite database `crawler.db` is
created next to the `backend/` package on first run.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (usually `http://127.0.0.1:5173`). The Vite dev
server proxies `/index`, `/search`, `/metrics`, `/jobs`, `/settings`, and
`/embeddings` to the backend.

### CLI (no UI required)

```bash
# Crawl
python -m backend.cli index https://en.wikipedia.org/wiki/Web_crawler 1 --max-urls 50 --rate 2

# Search the in-memory + persisted index
python -m backend.cli search "search engine" --limit 10

# Inspect known jobs
python -m backend.cli status
```

The `search` subcommand prints JSON shaped like:

```json
[
  {
    "relevant_url": "https://example.com/foo",
    "origin_url": "https://example.com/",
    "depth": 1
  }
]
```

which matches the assignment-required triple `(relevant_url, origin_url, depth)`.

## API quick reference

### Indexing

- `POST /index` with `{ "origin": "https://...", "k": 2, "max_urls_to_visit": 500, "rate_limit_per_sec": 1.0 }`
  returns `{ "job_id": "<uuid>" }`.

### Search

- `GET /search?query=...&limit=20` returns
  ```json
  {
    "triples": [
      { "relevant_url": "...", "origin_url": "...", "depth": 1 }
    ],
    "results": [
      { "relevant_url": "...", "origin_url": "...", "depth": 1, "score": 0.83, "title": "..." }
    ]
  }
  ```
- `GET /search/semantic?query=...&limit=20` returns the same shape using
  MiniLM cosine similarity.

### Jobs and metrics

- `GET /metrics` - aggregated counters and a `jobs_summary` list.
- `GET /jobs/{id}` - full per-job detail (frontier preview, events).
- `POST /jobs/{id}/pause` and `POST /jobs/{id}/resume`.
- `POST /jobs/{id}/rate-limit` with `{ "rate_limit_per_sec": 2.0 }`.
- `POST /settings/queue-limit` with `{ "global_queue_limit": 1500 }`.

### Embeddings

- `GET /embeddings/status`
- `POST /embeddings/start` with `{ "rate_limit_per_sec": 1.0, "max_pages": 500 }`
- `POST /embeddings/pause`
- `POST /embeddings/rate-limit` with `{ "rate_limit_per_sec": 0.5 }`
- `POST /embeddings/clear`

## How back pressure works

- A single `CrawlerService` instance owns a counter `_global_queued_urls`
  bounded by `global_queue_limit` (default 1000). All running jobs share that
  cap.
- When the cap is reached, `_try_reserve_global_queue_slot` returns false,
  link discovery for any worker spins on a short sleep, and the per-job and
  global `backpressure_state` flips from `normal` to `high` to `queue_full`.
- Per-job throttling is a simple monotonic-clock-based delay so each worker
  obeys the configured `rate_limit_per_sec`.
- The dashboard surfaces queue depth, back pressure state, and active worker
  count, so a human operator can react (lower the rate, raise the cap, pause
  a job) without redeploying.

## Searching while indexing is active

The crawler writes each fetched page directly into the in-memory inverted
index (`indexer.IndexService.add_page`). `IndexService.search` takes a small
re-entrant lock around its read; the FastAPI search endpoint reads from the
same singleton. As a result, queries fired while a crawl is still running
already see every page that has been processed up to that moment - no
restart, no re-index, no pause.

This is also exactly how the system would behave if `search` was called from
a separate process talking to the same SQLite database: the snapshot is
flushed regularly and the lexical index can be rebuilt from `pages` at any
time. For a real production split, see [`recommendation.md`](./recommendation.md).

## Resumability after interruption

- The `jobs`, `job_visited`, and `job_frontier` tables capture the full
  recoverable state of every crawl job. `_persist_state` is called on every
  worker tick (with a small batching/debounce) and on pause/resume.
- On startup, `app.py` calls `init_db()`, replays `pages` into the in-memory
  index via `add_snapshot_page`, and registers each persisted job. Any job
  that was `running` at shutdown becomes `paused` and can be resumed from
  the dashboard or by calling `POST /jobs/{id}/resume`.

## Multi-agent workflow

The end-to-end build was split across the following AI agents (with a human
acting as system designer / final reviewer):

- `system_architect`: produced the high-level architecture.
- `crawler_agent`: owned `crawler.py` and back pressure design.
- `indexer_agent`: owned the lexical inverted index in `indexer.py`.
- `semantic_agent`: owned `semantic_index.py` and the embedding engine.
- `api_agent`: owned the FastAPI surface and the response shapes.
- `ui_agent`: owned the React dashboard.
- `qa_agent`: produced the validation checklist and the resumability tests.
- `doc_agent`: produced PRD, README, recommendation, and this document.

For the prompts, hand-offs, conflicts, and decisions, read
[`multi_agent_workflow.md`](./multi_agent_workflow.md) and the per-agent
files in [`agents/`](./agents).

## Limitations (current scope)

- Single-process. Horizontal scaling is described but not implemented.
- No `robots.txt` enforcement and no per-domain crawl budget.
- Lexical ranking uses TF/IDF, not BM25.
- Semantic ranking quality depends on `all-MiniLM-L6-v2` and on how much of
  the page text is captured in the persisted snippet (2 KB cap).
- The dashboard polls every 2 seconds; there is no WebSocket push.

## License / Notes

This project is coursework. Crawl responsibly: only point it at sites you own
or that explicitly allow automated crawling.
