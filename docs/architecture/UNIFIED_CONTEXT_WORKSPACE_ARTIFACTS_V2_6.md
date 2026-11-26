# Unified Context, Workspace & Artifact Management — V2.6

## Context layers

- Runtime Environment: verified runtime, models, tools and permissions.
- Conversation Context: current Chat and message history.
- Business Context: persisted Proposal/Project/task selection and pending decisions.
- Workspace Context: the managed execution location for temporary, project or global work.
- Artifact Context: registered outputs, versions, validation and delivery state.

The Main Agent prompt receives the current Chat's persisted Business Context from SQLite. A durable Proposal binding takes precedence over parsing message text. Ambiguous historical references are not guessed.

## Workspace types

| Type | Root | Governance |
|---|---|---|
| temporary | `workspaces/temporary/{workspace_id}` | No Project approval required |
| project | `workspaces/projects/{project_id}` | Associated with a formal Project |
| global | `global/outputs/{workspace_id}` | No Project association |

Each workspace contains `inputs/`, `workspace/`, and `outputs/`. Project workspaces also contain `deliverables/`.

## Artifact lifecycle

Artifacts are registered in `sys_artifacts`. Re-registering the same filename in one workspace creates a new version and links it to the prior Artifact. Registration verifies that the file exists within its workspace, calculates its SHA-256 checksum and size, and creates execution evidence. Status transitions are validated by the backend; delivery requires prior approval. Downloads are served by the backend using the registered artifact ID. A generated file is not a formal deliverable merely because it exists; `approved` and `delivered` are distinct states.

## Persistence

- `sys_business_contexts`: one durable current business context per Chat.
- `sys_workspaces`: managed workspace metadata and lifecycle.
- `sys_artifacts`: file metadata, integrity checksum and review state.
- `sys_execution_evidence`: backend-confirmed actions and outcomes.

Existing Proposal, Project, Team Plan, lifecycle and activity tables are retained. `sys_team_plans` is reused; no replacement Team Plan table is introduced.

## Security boundaries

- File paths are resolved and constrained to the registered workspace root.
- Artifact registration rejects missing files and path traversal.
- Downloads resolve the path again and verify that the file still exists.
- The API does not expose arbitrary filesystem browsing or permit an Agent to register an outside path.

## Operational limitations

Temporary workspace expiry is metadata only in this release; no background cleanup scheduler is enabled. Artifact generation must be performed by an authorized execution capability before registration. Existing Chat transcripts are not mined to infer a Proposal binding where the selection is ambiguous.


## Agent Capability and Tool Assignment (V2.6.1)

Capabilities and Tools are independent registry concepts. Agent configuration assigns Capability IDs and may separately assign direct Tool names. The capability catalog declares `grants_tools`; the runtime computes effective tools as `(inherited capability tools ∪ direct tools) − denied tools`. Explicit denials take precedence. Only assignable capabilities can grant tools. Legacy descriptive capability labels are retained as notes and are not executable permissions. Specialist Runtime registers mutating tools only when the effective permission set allows them; workspace root and platform access policy remain additional constraints.
