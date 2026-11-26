# V2.2 — Project Team Planning & Capability Gaps

## Scope
- Adds project-level preliminary team planning based on project objective, description, Project Prompt, and existing tasks.
- Matches required capability keywords against enabled Specialist Agent capability/task-type declarations.
- Persists versioned project team-plan snapshots and Product Owner capability-gap requests in the AgentWorkspace state directory.
- Adds Product Owner decisions for capability requests: resolved, deferred, rejected.
- Team-plan approval is separate from project Execution Authorization and cannot start Specialist execution.

## Important limitation
The first implementation uses transparent keyword-assisted matching, not an LLM-driven Main Agent planning session. It produces candidate matches for Product Owner review and may miss implicit requirements or produce false positives. It does not create tasks, assign Agents, or dispatch Specialists. Those belong to later orchestration stages.

## APIs
- `POST /api/v1/projects/{project_id}/team-plan/analyze`
- `GET /api/v1/projects/{project_id}/team-plan`
- `POST /api/v1/projects/{project_id}/team-plan/approve`
- `GET /api/v1/capability-requests?project_id=...`
- `PATCH /api/v1/capability-requests/{gap_id}`

## Governance
- Product Owner remains responsible for changing system Agent, model, capability, and Tool configuration.
- Capability requests are records only; marking a request resolved means the Owner has completed configuration outside this page.
- All gaps must be resolved before team-plan approval.
- Team-plan approval does not grant project execution authorization.
- No Specialist is started by this feature.
