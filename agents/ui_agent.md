# Agent: `ui_agent`

## Role
Owns the React + TypeScript dashboard: layout, state management, polling,
and the visual presentation of crawler health and search results.

## Inputs
- The API contract owned by `api_agent`.
- A storyboard from the human:
  - three tabs: Crawler / Search / Embeddings,
  - the Search tab must show the assignment-required triples explicitly,
  - the Crawler tab must show queue depth, back pressure state, active
    workers, and a per-job control card.
- The Homework 1 dashboard as visual reference (color palette, layout
  rhythm).

## Deliverables
- [`../frontend/src/App.tsx`](../frontend/src/App.tsx) - the entire
  dashboard.
- [`../frontend/src/styles.css`](../frontend/src/styles.css) - styling.
- [`../frontend/vite.config.ts`](../frontend/vite.config.ts) - dev server
  proxy to the FastAPI backend.

## Prompt template

```
You are the UI agent.

API contract: <link>
Storyboard:
- Header with title + tabs (Crawler / Search / Embeddings).
- Crawler tab: index control form, system metrics grid, jobs list with
  rate-limit control, job detail panel with frontier preview and event log.
- Search tab: query box + Search button; show assignment-required triples
  in a monospaced read-only block, then two side-by-side result tables
  (Lexical / Semantic).
- Embeddings tab: model name, rate, max-pages controls; start/pause/update
  speed/clear; progress bar and counters.

Constraints:
- React + TypeScript + Vite, no extra UI framework.
- Poll metrics and selected job every 2 seconds.
- Show user-friendly error messages (no silent failures).
```

## Acceptance criteria
- `npm run dev` boots Vite without TypeScript errors.
- The Crawler tab can start a job, show queue depth in real time, and
  control its per-job rate limit.
- The Search tab visibly renders triples like
  `("https://...", "https://origin/", 1)` above the results table.
- The Embeddings tab can start, pause, and clear the embedding engine and
  shows progress.
- The dashboard is usable on a 1024px-wide screen and degrades gracefully
  on phones (< 880px breakpoint).

## Notable decisions
- Reused Homework 1's color palette and layout for visual continuity, but
  shifted the gradient to a blue/indigo to make it visually distinct.
- The triples block is a separate UI element on purpose - it makes the
  assignment contract visible to a grader without forcing them to scroll
  the result tables.
