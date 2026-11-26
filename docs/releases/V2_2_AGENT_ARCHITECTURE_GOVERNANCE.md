# LocalAgentUI V2.2 — Agent Architecture & Governance Foundation

## Base version
This release is based on `LocalAgentUI_V2_1_UI_Prompt_Upgrade.zip`.

## Implemented in this iteration

### 1. Prompt architecture
- Prompt assembly explicitly orders P0 Platform Safety, P1 System Core, P2 Main Agent Role, P3 Approved Global Rules, P4 Project Instructions, P5 Session Instructions, and optional P6 Current User Request.
- P3 is optional and falls back to an explicit empty-state rule.
- Registered specialist identities are injected into P5 as a catalogue; the catalogue does not grant tools or permissions.
- Main Agent instructions now distinguish Specialist Agents from Tools and define planning, dispatch, evidence, and Hybrid Governance boundaries.

### 2. Specialist Agent runtime
- `backend/agents/agent_registry.py` loads specialist identities from role Markdown files; `main_agent.md` is excluded.
- `backend/agents/agent_runtime.py` executes an isolated specialist model call using the specialist's role prompt.
- `backend/agents/agent_dispatcher.py` validates and routes dispatch requests.
- `backend/agents/agent_result_manager.py` records dispatch results in memory for the current request lifecycle.
- Main chat exposes `delegate_to_specialist` as a dispatch operation. The backend invokes the dispatcher rather than treating the specialist as a normal tool handler.

**Current runtime boundary:** specialist calls currently receive task text and context only. They do not inherit Main Agent tools, workspace file access, database access, or write permissions. Those capabilities must be explicitly designed and passed in a later integration step.

### 3. Governance and planning primitives
- `AuthorizationManager` distinguishes autonomous planning activities from reserved Product Owner decisions.
- `ApprovalManager` defines allowed lifecycle transitions from Proposal Submitted through Accepted/Rejected.
- `ProjectPlanner` validates required planning sections and task dependency references.

**Persistence boundary:** these are service-layer primitives in this iteration. They are not yet wired into the existing proposal/project database lifecycle. Existing API and database behaviour is intentionally preserved pending a schema/API integration pass.

### 4. Empty and malformed model responses
- Main chat validates the OpenAI-compatible response envelope before reading `choices[0].message`.
- A blank assistant response is retried once with an explicit request for text or a valid tool call.
- Repeated blank output is reported as a model response failure rather than being presented as a normal answer.

## Preserved
- Frontend source and styling
- Existing SQLite database and schema files
- Existing proposal and project API modules
- Existing workspace file permission model

## Verification performed
- `python -m compileall -q backend` — passed.
- `python -m unittest backend.test_prompt_manager -v` — 2 tests passed.

No live Ollama call, full UI workflow, database migration, or real specialist dispatch against a running model was performed as part of this package build.

## Next integration work
1. Persist dispatch records and task/agent assignments in the project database.
2. Add scoped specialist tool capabilities through an explicit capability grant model.
3. Connect authorization checks to proposal approval, project creation, task execution, and final acceptance APIs.
4. Connect ProjectPlanner to proposal generation and task persistence.
5. Run live end-to-end tests for empty responses, dispatch, failure handling, and governance transitions.

## Governance integration update — 2026-11-24

The proposal and project APIs now persist and enforce the staged project lifecycle through the additive `sys_project_lifecycle` table (schema migration v2). Existing project/proposal records are backfilled during migration.

Lifecycle command flow in Chat:

1. `approve proposal <proposal-id>` — records **Approved in Principle** only; no project or tasks are created.
2. `authorize planning for proposal <proposal-id>` — grants planning authority only.
3. `formally approve proposal <proposal-id>` — creates the formal project and its approved task breakdown; execution remains blocked.
4. `authorize execution for project <project-id>` — explicitly authorises execution.
5. Tasks cannot transition to `in_progress` before execution authorisation.
6. `POST /api/v1/projects/{project_id}/submit-for-acceptance` — submits a project with no incomplete tasks for Product Owner acceptance.
7. `POST /api/v1/projects/{project_id}/accept` — records final acceptance and closes the project.

Direct project creation is treated as formal project creation by the user, but does not grant execution authorisation. Project closure and task execution are guarded by lifecycle state. The database migration is additive; the original v1 schema migration is not modified.

Validation performed for this update:
- Python compile check across backend modules.
- Isolated SQLite migration/bootstrap to schema v2.
- End-to-end governance smoke flow: proposal submission → approval in principle → planning authorization → formal project approval → execution blocked before authorization → execution authorization → task start → pending acceptance → final acceptance.
