# Database Schema v2.0

## Design rules

- Single-user local SQLite deployment.
- All Local Agent persistence tables use the `sys_` prefix and lowercase `snake_case`.
- UUID strings are used for application-generated primary keys.
- Timestamps are stored as UTC ISO-8601 text.
- Foreign-key enforcement is enabled for every connection.
- Agent assignment history is retained by closing an active assignment with `unassigned_at`; reassignment inserts a new row.
- Approval is represented by a generic `sys_approval_requests` entity and linked to proposals.
- Migration versions are application-owned records in `sys_schema_migrations`; SQLite `PRAGMA schema_version` remains an internal schema cookie only.

## Tables

| Table | Purpose |
|---|---|
| `sys_agents` | Main Agent and specialist Agent definitions, roles, status and permissions |
| `sys_projects` | Approved formal projects and their lifecycle |
| `sys_project_proposals` | Project proposal content, lifecycle and approved baseline |
| `sys_tasks` | Project tasks, hierarchy, status, timing and completion criteria |
| `sys_task_assignments` | Full Agent assignment/reassignment history |
| `sys_task_dependencies` | Finish-to-start task dependencies |
| `sys_task_executions` | Task execution attempts and outcomes |
| `sys_progress_records` | Project/task progress snapshots |
| `sys_risks` | Project risks and issues |
| `sys_decisions` | Project-level decisions and options |
| `sys_deliverables` | Deliverable lifecycle and acceptance |
| `sys_test_records` | QA/test evidence for deliverables |
| `sys_approval_requests` | Generic approval request and decision record |
| `sys_tools` | Tool registry metadata and permission scope |
| `sys_tool_versions` | Versioned tool implementation/configuration metadata |
| `sys_agent_tools` | Agent-to-tool permission assignments |
| `sys_tool_executions` | Tool invocation inputs, outputs and execution status |
| `sys_activity_logs` | Project/task/Agent audit events |
| `sys_schema_migrations` | Applied migration version, checksum and timestamp |

## Startup lifecycle

1. Open the configured SQLite database and apply connection pragmas.
2. Detect an un-migrated legacy prototype schema; fail startup with a reset instruction rather than silently deleting data.
3. Apply pending migrations inside an explicit transaction.
4. Verify checksums for already-applied migrations; applied migration files are immutable.
5. Seed built-in Agents idempotently.
6. Validate the expected table inventory, application schema version, SQLite integrity and foreign-key integrity.
7. Only then allow FastAPI to finish startup and accept requests.

The explicit `--reset-prototype` path deletes the old database and its SQLite sidecar files, then performs the same bootstrap sequence. It is never called by normal application startup.
