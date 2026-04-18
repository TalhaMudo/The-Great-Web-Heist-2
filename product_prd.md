# Product Requirements Document - The Great Web Heist 2 (Multi-Agent Build)

This PRD is written for an AI coding agent (or a human developer) to (re)build
the system from scratch. It captures the same crawler/search functionality as
Project 1, but the development process is required to use a multi-agent
workflow (see [`multi_agent_workflow.md`](./multi_agent_workflow.md)).

## 1. Problem Statement

We need a single-machine web crawler and search engine that:

- recursively crawls from an origin URL up to depth `k`, never visiting the
  same page twice for a job;
- exposes a `search(query)` API returning the assignment-required triples
  `(relevant_url, origin_url, depth)`;
- supports searching while indexing is still in progress, so newly discovered
  pages appear in results as soon as they are indexed;
- includes back pressure (queue depth cap and per-job rate limit) so the system
  controls load on a single machine;
- ships with a simple UI and CLI that make it easy to start indexing, run
  search, and view system state (queue depth, back pressure, job status);
- can resume after interruption without restarting from scratch (nice-to-have).

## 2. Goals

| ID  | Goal                                                                                                                |
| --- | ------------------------------------------------------------------------------------------------------------------- |
| G1  | `index(origin, k)` performs a depth-limited, deduplicated crawl on a single machine.                                |
| G2  | `search(query)` returns triples `(relevant_url, origin_url, depth)`; results update live during active crawls.      |
| G3  | The system enforces back pressure via a global queue cap and per-job request rate limit.                            |
| G4  | A React dashboard and a Python CLI both let a user kick off indexing, run search, and inspect runtime state.        |
| G5  | Crawl state and indexed pages persist to SQLite so search works after restart and crawls can resume.                |
| G6  | Optional: an additional semantic search ranking using `all-MiniLM-L6-v2` embeddings.                                |
| G7  | Development uses a documented multi-agent workflow (system architect, crawler agent, search agent, UI agent, etc.). |

## 3. Non-Goals

- Internet-scale, multi-machine crawling.
- Production-grade ranking quality (BM25, learning-to-rank).
- Full politeness policies (robots.txt, per-domain budgets) - mentioned only
  in [`recommendation.md`](./recommendation.md).
- Authentication, multi-tenant, or multi-user features.
- Strong security hardening beyond what is needed for a localhost demo.

## 4. User Stories

- _As a student_, I open the dashboard, enter a seed URL and depth `k`, and
  start an indexing job. I see queue depth, processed URL counts, and back
  pressure state update in near real time.
- _As a student_, I run a query in the search panel **while** the crawl is
  still progressing and I see the lexical results panel grow as new pages get
  indexed.
- _As an instructor_, I can point at the dashboard and at the multi-agent
  workflow document to explain how AI agents collaborated on this build.
- _As an automation user_, I can run `python -m backend.cli index <url> <k>`
  in a terminal and then `python -m backend.cli search "<query>"` to get
  JSON-formatted triples.
- _As a developer_, I can stop the backend, restart it, and immediately search
  pages indexed in earlier runs because the SQLite snapshot is reloaded at
  startup.

## 5. Functional Requirements

### 5.1 Indexing

- `POST /index` accepts `{ origin: string, k: int, max_urls_to_visit?: int, rate_limit_per_sec?: float }`.
- Spawns an asynchronous crawl job identified by a UUID `job_id`.
- The crawler:
  - normalizes URLs (`urljoin`, `urldefrag`, scheme allowlist `http/https`);
  - keeps a per-job `visited` set so the same URL is never crawled twice;
  - uses a fixed worker pool (default 5) reading from an `asyncio.Queue`;
  - throttles fetches per job using a configurable request rate (`req/s`);
  - shares a global queue capacity across all jobs to enforce back pressure;
    when the global cap is hit, link discovery pauses and back pressure state
    moves to `queue_full`;
  - records each fetched page's title and tokenized snippet to SQLite so the
    in-memory index can be rebuilt at startup;
  - persists `visited` and `frontier` periodically and on pause/restart so a
    job can be resumed.

### 5.2 Search

- `GET /search?query=...&limit=...` returns:
  - `triples`: `[{ relevant_url, origin_url, depth }]` (assignment contract);
  - `results`: same data plus optional `score` and `title` for the UI.
- Lexical ranking uses an in-memory inverted index with TF normalized by
  document length and IDF computed from the current corpus, so newly added
  pages immediately influence ranking.
- `GET /search/semantic?query=...&limit=...` returns the same response shape
  using cosine similarity over MiniLM vectors stored in `page_embeddings`.

### 5.3 Job Control and Observability

- `GET /metrics`: aggregated counters (`processed_urls`, `discovered_urls`,
  `duplicate_urls`, `failed_urls`, `queued_urls`, `queue_max`,
  `backpressure_state`, `active_workers`) plus a `jobs_summary`.
- `GET /jobs/{id}`: full per-job detail including a `frontier_preview` and the
  most recent events.
- `POST /jobs/{id}/pause`, `POST /jobs/{id}/resume`,
  `POST /jobs/{id}/rate-limit`, `POST /settings/queue-limit`.
- `GET /embeddings/status`, `POST /embeddings/start|pause|rate-limit|clear`.

### 5.4 UI

- React + TypeScript + Vite dashboard with three modes:
  - **Crawler**: index control + system metrics + per-job cards + job detail.
  - **Search**: side-by-side lexical and semantic results, with a panel that
    explicitly renders the required triples.
  - **Embeddings**: control panel for the optional semantic engine.

### 5.5 CLI

- `python -m backend.cli index <origin> <k> [--max-urls N] [--rate R]`
- `python -m backend.cli search "<query>" [--limit N]` returns JSON triples.
- `python -m backend.cli status`

### 5.6 Persistence and Resumability

- SQLite (`crawler.db`) stores: `pages`, `jobs`, `job_visited`,
  `job_frontier`, `job_events`, `page_embeddings`.
- On startup the FastAPI app rebuilds the in-memory index from `pages` and
  re-registers all known jobs (jobs that were `running` are demoted to
  `paused`, ready to be resumed).

## 6. Constraints

- Backend in **Python 3.10+**, using only the standard library
  (`urllib`, `html.parser`, `asyncio`, `sqlite3`, `re`) for the core crawler
  and indexer logic. The only third-party runtime dependencies are FastAPI +
  uvicorn (HTTP server) and `sentence-transformers` (optional semantic).
- Frontend in **TypeScript** with React + Vite.
- Single process, single machine. Concurrency uses `asyncio` workers.

## 7. Acceptance Criteria

- Starting a crawl from an HTML page reachable on the public internet yields a
  growing `pages` table and a non-zero `processed_urls` counter.
- Running `search` while the crawl is still active returns more results over
  time without restarting the backend.
- Reducing `global_queue_limit` below the current queue depth causes the
  global metrics endpoint to report `backpressure_state="queue_full"` and link
  discovery to pause.
- Killing and restarting the backend lets the user immediately search the
  pages that were indexed earlier (rebuilt from SQLite).
- The CLI command `search` returns JSON of the form
  `[{"relevant_url":..., "origin_url":..., "depth":...}, ...]`.
- The repository contains `multi_agent_workflow.md` and `agents/*.md` files
  that explain how AI agents collaborated on the build.
