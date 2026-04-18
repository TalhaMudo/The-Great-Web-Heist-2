# Agent: `doc_agent`

## Role
Owns the human-facing documentation. Synthesizes the work of the other
agents into a coherent story for graders and future maintainers.

## Inputs
- All other agent files in this folder.
- The current state of the codebase.
- The assignment brief (so the docs explicitly satisfy the rubric).

## Deliverables
- [`../product_prd.md`](../product_prd.md) - PRD aimed at an AI builder.
- [`../README.md`](../README.md) - end-user / developer overview, install,
  run, and API reference.
- [`../recommendation.md`](../recommendation.md) - 1-2 paragraphs on
  production deployment.
- [`../multi_agent_workflow.md`](../multi_agent_workflow.md) - this
  workflow document.
- [`./README.md`](./README.md) and the per-agent files in this folder.

## Prompt template

```
You are the documentation agent.

Inputs:
- Assignment brief: <pasted brief>
- Code: ../backend, ../frontend
- Agent definitions: ../agents/*.md

Produce:
- product_prd.md aimed at an AI coder; include goals, non-goals, user
  stories, functional requirements, constraints, and acceptance criteria.
- README.md with: what it does, layout, install, run (backend / frontend /
  CLI), API quick reference, back pressure note, search-while-indexing
  note, resumability note, and a pointer to the multi-agent docs.
- recommendation.md: 1-2 paragraphs on production deployment.
- multi_agent_workflow.md: roster, communication model, phases, decisions,
  prompts, validation checklist, lessons learned.

Style: precise, no marketing copy, file paths as inline code.
```

## Acceptance criteria
- Every required deliverable from the assignment exists.
- The README's run instructions actually work (verified by `qa_agent`).
- The PRD's acceptance criteria match the QA checklist.
- The multi-agent doc names every agent in
  [`./README.md`](./README.md) and explains how decisions were made.

## Notable decisions
- Wrote the PRD specifically for an AI builder (per the assignment), so it
  reads more like a spec than a pitch.
- Chose to keep the recommendation at exactly two paragraphs, as the
  assignment requested.
