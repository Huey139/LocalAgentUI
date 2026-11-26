# Database Schema — Current Version 4

The application currently uses **Schema v4**. Schema version is independent of the application release version in `VERSION`. Applied migrations are immutable; schema changes must be introduced as a new migration.

## System tables (25)

| Table | Responsibility |
|---|---|
| `sys_agents` | Agent profiles and configuration |
| `sys_projects` | Formal projects |
| `sys_project_proposals` | Proposals, independent from formal Projects |
| `sys_project_lifecycle` | Project governance and lifecycle transitions |
| `sys_team_plans` | Versioned Team Plans associated with Proposal or Project |
| `sys_tasks` | Project tasks |
| `sys_task_assignments` | Agent/task assignments |
| `sys_task_dependencies` | Task dependency relationships |
| `sys_task_executions` | Task execution records |
| `sys_progress_records` | Progress history |
| `sys_risks` | Project risks |
| `sys_decisions` | Recorded project decisions |
| `sys_deliverables` | Formal project deliverables |
| `sys_test_records` | Test and verification records |
| `sys_approval_requests` | Generic approval request records |
| `sys_tools` | Tool registry metadata |
| `sys_tool_versions` | Tool version history |
| `sys_agent_tools` | Agent/tool capability association |
| `sys_tool_executions` | Tool execution records |
| `sys_activity_logs` | Business activity audit history |
| `sys_schema_migrations` | Applied migration versions and checksums |
| `sys_business_contexts` | Durable current business-object binding per Chat |
| `sys_workspaces` | Temporary, Project and Global Workspace metadata |
| `sys_artifacts` | Registered file outputs, checksums, versions and review state |
| `sys_execution_evidence` | Backend-confirmed action outcomes |

## New v4 relationships

- One `sys_business_contexts` record is maintained per `chat_id`; it can bind a Proposal, Project, Task or Team Plan.
- A `sys_workspace` may be temporary, project-scoped or global. Project workspaces reference `sys_projects`; chat association is independent of Project association.
- Each `sys_artifacts` row belongs to one workspace. Project association is also stored for filtering and reporting.
- `sys_execution_evidence` records backend-confirmed context binding and artifact registration, and can also record workflow actions.

## Migration history

- v001: initial versioned system schema.
- v002: Project lifecycle governance.
- v003: independent, versioned Team Plans.
- v004: Business Context, Workspace, Artifact Registry and execution evidence.

`docs/architecture/DATABASE_SCHEMA_V2.md` is retained as historical documentation for the original Schema v2 baseline; use this document for the current schema.
