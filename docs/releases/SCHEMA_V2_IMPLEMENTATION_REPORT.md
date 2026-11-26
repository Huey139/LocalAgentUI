# Local Agent — Database Schema v2.0 Implementation Report

## Delivered

- Replaced the legacy unversioned SQLite schema with a formal 19-table `sys_` schema.
- Added `backend/db/` modules for bootstrap, migration management, schema validation, seed management and versioned migration definitions.
- Added atomic migration execution without `sqlite3.executescript()` implicit transaction behaviour.
- Added migration checksum verification and explicit rejection of databases newer than the application supports.
- Added idempotent seeding for the seven built-in Agent roles.
- Added a generic Approval Request entity and linked each Project Proposal to its approval record.
- Preserved full Agent assignment/reassignment history using `unassigned_at` and new assignment rows.
- Added database integrity, foreign-key, expected-table and application-version validation before FastAPI startup completes.
- Switched FastAPI database initialization to its lifespan handler; bootstrap failures prevent the API from accepting traffic.
- Updated Project and Proposal APIs to use the new `sys_` tables while preserving existing API paths and response conventions.
- Updated schema inspection metadata to distinguish SQLite's internal `PRAGMA schema_version` from the application migration version.
- Added an explicit `RESET_PROTOTYPE_DB.command` for the one-time destructive replacement of legacy prototype databases. Normal startup never drops or clears tables.
- Updated setup, deployment and schema documentation.

## Schema inventory

The 19 tables are `sys_agents`, `sys_projects`, `sys_project_proposals`, `sys_tasks`, `sys_task_assignments`, `sys_task_dependencies`, `sys_task_executions`, `sys_progress_records`, `sys_risks`, `sys_decisions`, `sys_deliverables`, `sys_test_records`, `sys_approval_requests`, `sys_tools`, `sys_tool_versions`, `sys_agent_tools`, `sys_tool_executions`, `sys_activity_logs` and `sys_schema_migrations`.

## Verification performed

- `python -m compileall -q backend` — passed.
- `python -m backend.smoke_test_database` — passed using an isolated temporary database.
- Schema bootstrap and repeat bootstrap — passed.
- Seven Agent seed records and migration idempotency — passed.
- Project/Task API creation, assignment/reassignment history and status transitions — passed.
- Proposal submission, generic approval record creation, approval and Project/Task creation — passed.
- Proposal rejection without Project creation — passed.
- Explicit legacy database detection and reset — passed using a temporary test database.
- Delete audit trigger and foreign-key cleanup — passed.
- Schema inspection service application-version reporting — passed.
- FastAPI route registration — passed.

## Operational note

A clean installation creates the database automatically. For an existing installation containing the old prototype tables, run `RESET_PROTOTYPE_DB.command` once and type `RESET` before starting the application. This deletes the old prototype SQLite database and its WAL/SHM sidecars. Normal startup is non-destructive.

## Scope boundary

The schema includes Tool Registry, Tool Version, Agent-Tool Permission and Tool Execution persistence tables. The current runtime ToolManager remains code-registered; persisting live ToolManager registrations into these tables is a separate integration phase and is not claimed as implemented here. Full autonomous specialist execution and orchestration remain outside this database refactor.
