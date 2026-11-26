# Phase 2 — SQLite & Project Management Foundation

## Implemented

- Added `backend/database.py` with a local SQLite connection manager and idempotent schema initialization.
- Added 12 relational tables, foreign keys, status/priority/duration checks and query indexes.
- Added idempotent built-in Agent role seeding (Main Agent, Developer, SQL Agent, Data Analyst, QA Agent, Research Agent, File Manager).
- Added `backend/project_api.py` with basic Project, Task and Agent APIs, task assignment, dependency insertion with cycle detection, and activity log retrieval.
- FastAPI initializes the database at startup. No Ollama call is made for database initialization.
- Default database file: `data/local_agent.db`; override with `LOCAL_AGENT_DB_PATH`.
- Existing chat history and Workspace storage remain unchanged.

## API endpoints

- `GET /api/v1/database/status`
- `GET, POST /api/v1/projects`
- `GET, PATCH /api/v1/projects/{project_id}`
- `GET /api/v1/projects/{project_id}/tasks`
- `POST /api/v1/tasks`
- `GET, PATCH /api/v1/tasks/{task_id}`
- `POST /api/v1/tasks/{task_id}/assign`
- `POST /api/v1/tasks/{task_id}/dependencies`
- `GET /api/v1/agents`
- `PATCH /api/v1/agents/{agent_id}`
- `GET /api/v1/activity`

## Not yet implemented

- Frontend Project/Task/Agent screens are not yet connected to these APIs.
- Specialist Agent execution orchestration and real task worker queue are not implemented in this phase.
- Risks, decisions, deliverables and QA tables exist, but their full CRUD/workflow endpoints are future work.

## Local verification

Start the backend, then visit `/api/v1/database/status` or run `sqlite3 data/local_agent.db ".tables"`.
