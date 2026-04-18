# Agent: `qa_agent`

## Role
Owns the validation checklist and the regression strategy. Runs the system
end to end and reports failures back to the human with reproduction steps.

## Inputs
- The acceptance criteria from `product_prd.md` Section 7.
- The 10-item checklist in
  [`../multi_agent_workflow.md`](../multi_agent_workflow.md) Section 7.
- A running backend (`uvicorn backend.app:app`) and either the dashboard or
  the CLI as a driver.

## Deliverables
- A pass/fail report against the checklist.
- A list of repro steps for any failure, routed back to the agent that
  owns the affected module.
- A short note about test coverage gaps (what is _not_ verified by the
  manual checklist - e.g. very large frontier behavior) so the human can
  decide whether to extend the scope.

## Prompt template

```
You are the QA agent.

Checklist: ../multi_agent_workflow.md Section 7

For each item, list:
- What you ran (curl command, CLI command, or UI action).
- What you observed.
- Pass / Fail / N/A and why.

If anything fails, produce a minimal repro and a one-sentence guess at
which agent's deliverable is the source of the regression.
```

## Acceptance criteria
- All checklist items have a pass/fail entry.
- Any failure has a clear owner (one of the other agents) so the human can
  re-route the fix.

## Notable decisions
- QA is manual on purpose: this is a course project and adding pytest
  scaffolding would distract from the multi-agent narrative. A production
  evolution would add unit tests for `tokenize`, `normalize_url`, and the
  `IndexService.search` ranking math, plus an end-to-end test that crawls
  a small synthetic site served by `python -m http.server`.
- One scripted end-to-end smoke test was added at `.smoketest/run_smoke.py`.
  It boots a local static site, runs `index`, polls `search` while the
  crawl is active (Q4), inspects the assignment-shaped triples (Q3),
  and exercises pause + resume (Q6). The script is the canonical "did the
  hand-off between agents actually produce a working system?" check.

## Findings reported to other agents
- **2026-04 / crawler_agent:** during pause+resume the smoke test caught
  that workers cancelled inside `await fetch_html(url)` left
  `ctx.active_requests` greater than zero, so the post-resume completion
  gate (`queue.empty() and active_requests == 0`) never fired and the job
  hung in `running` forever. Repro: pause a job within ~50ms of starting,
  resume it, observe that `JobStatus` never reaches `COMPLETED`. Routed to
  `crawler_agent`, which wrapped the fetch in `try/finally` and added a
  defensive reset in `pause_job`. See decision #13 in
  `multi_agent_workflow.md`.
