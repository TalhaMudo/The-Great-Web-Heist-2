# Agent: `indexer_agent`

## Role
Owns the in-memory inverted index, tokenization, HTML-to-text extraction,
TF-IDF ranking, and the snapshot reload at startup.

## Inputs
- The architecture brief from `system_architect`.
- The persistence layer (`save_page`, `load_pages`) from `storage.py`.

## Deliverables
- [`../backend/indexer.py`](../backend/indexer.py) - `TextExtractor`,
  `tokenize`, `IndexService`, `index_service` singleton.
- Interface note describing:
  - the public methods (`add_page`, `add_snapshot_page`, `search`),
  - the response shape `(relevant_url, origin_url, depth, score, title)`,
  - the locking strategy (`threading.RLock`) used so that a search call
    issued during an active crawl always sees a consistent view.

## Prompt template

```
You are the lexical search index agent.

Architecture brief: <link>
Storage interface: storage.save_page(url, origin_url, depth, title, body_snippet)
                   storage.load_pages() -> list of tuples

Implement an in-memory inverted index in backend/indexer.py with:
- HTML to title/body extraction using only html.parser,
- regex tokenizer that lowercases and keeps [A-Za-z0-9]+ runs,
- inverted index: token -> {url: (url, origin_url, depth, tf)} where tf is
  the term frequency normalized by document length,
- search(query, limit) ranks documents by sum_t tf(t,d) * idf(t),
- re-indexing the same URL must NOT inflate its score (drop old postings),
- thread-safe so the FastAPI request loop and crawler workers can call it
  concurrently.
```

## Acceptance criteria
- `IndexService.search("query")` returns a non-empty list once at least one
  page has been added that contains a matching token.
- `add_page` followed by `add_page` for the same URL leaves the inverted
  index with exactly one posting per (token, url) pair.
- `add_snapshot_page` (used at startup) reproduces the same scores as
  `add_page` would have for the same `(title, body_snippet)` pair.

## Notable decisions
- Switched from raw "sum of token counts" (Homework 1) to TF normalized by
  document length plus IDF. The motivation was decision #4 in the workflow:
  produce ranking that does not penalize long pages.
- Postings are stored as `Dict[str, IndexEntry]` keyed by URL so re-indexing
  the same URL replaces (instead of appending) - this is decision #5 in the
  workflow doc.
- The lock is an `RLock` so callers that hold it can recursively call other
  index methods safely.
