# Agents

This folder contains a description of every AI agent that contributed to the
build of The Great Web Heist 2. Each file follows the same template:

- **Role** - one-sentence summary of what the agent owns.
- **Inputs** - what it reads before producing anything.
- **Deliverables** - the exact files / artifacts it produces.
- **Prompt** - the prompt template the human used to invoke it.
- **Acceptance criteria** - how the human decided the output was done.
- **Notable decisions** - anything that fed back into
  [`multi_agent_workflow.md`](../multi_agent_workflow.md).

The catalog of agents:

| File                                          | Owns                                     |
| --------------------------------------------- | ---------------------------------------- |
| [`system_architect.md`](./system_architect.md) | Module layout, API contract, persistence |
| [`crawler_agent.md`](./crawler_agent.md)       | `backend/crawler.py` + back pressure     |
| [`indexer_agent.md`](./indexer_agent.md)       | `backend/indexer.py` (TF-IDF)            |
| [`semantic_agent.md`](./semantic_agent.md)     | `backend/semantic_index.py` (MiniLM)     |
| [`api_agent.md`](./api_agent.md)               | `backend/app.py` (FastAPI surface)       |
| [`ui_agent.md`](./ui_agent.md)                 | `frontend/src/*` (React dashboard)       |
| [`qa_agent.md`](./qa_agent.md)                 | Validation checklist + repro steps       |
| [`doc_agent.md`](./doc_agent.md)               | PRD, README, recommendation, this folder |

For the workflow that ties them together, see
[`../multi_agent_workflow.md`](../multi_agent_workflow.md).
