# V2.2 Proposal-to-Project Lifecycle

## Delivered

- Proposal creation now saves a backend-generated Proposal ID as a `discussion` draft; it does not create a pending approval request or a Project.
- Proposal revisions are allowed during discussion and invalidate any previously generated Team Plan by marking it `stale`.
- Main Agent can revise an existing Proposal in follow-up turns in the same conversation through `revise_project_proposal`.
- Proposal-level Team Planning is available before a `sys_projects` row exists.
- Team Planning uses the Main Agent LLM and validates registered Specialist Agents, installed models, system Capabilities, registered/enabled Tools and Agent Tool permissions.
- Software/application/system proposals explicitly prompt for a distinct QA/testing workstream unless testing is excluded.
- Formal Project Approval requires a current Team Plan with at least one workstream, at least one ready registered Specialist and no unresolved validation gaps.
- The Product Owner's formal confirmation approves the Team Plan and creates the Project row in one database transaction.
- The Proposal stores the Project ID and approved baseline. The Team Plan is copied into the project-scoped Team Plan store.
- Formal approval is idempotent: retrying returns the existing Project ID.
- Formal Project creation does not create Task, Task Dependency or Task Assignment rows and does not authorise execution.

## Chat workflow

1. Ask Main Agent to prepare a project Proposal. It saves a discussion draft and returns a real Proposal ID.
2. Discuss objective, scope, deliverables, milestones, budget assumptions, timeline, risks and acceptance criteria. Main Agent saves revisions to the same Proposal.
3. Send `plan team for proposal <proposal-id>`.
4. Review the workstreams, proposed Specialist candidates and any configuration gaps. Fix Agent/Model/Capability/Tool/permission configuration and regenerate if necessary.
5. Send `formally approve proposal <proposal-id>` for the final confirmation and Project creation.
6. Verify the returned Project ID in the Projects page. The Project is in `planning`; execution is not authorised.

## Deferred to next release

- Task decomposition after formal Project creation.
- Task dependency creation and task-to-Agent assignment.
- Specialist dispatch and execution.
- Live Specialist issue reporting to Main Agent.
- Main Agent operational decision policy, risk classification and escalation to Product Owner.
- Execution authorisation and execution monitoring integration.

## Validation

- `python -m compileall -q backend` — passed.
- `python -m unittest discover -s . -p 'test_*.py' -q` — 32 tests passed.
- Isolated TestClient smoke test — Proposal persisted, LLM Team Plan route exercised with mocked Ollama/catalogs, formal approval created one Project, zero Task rows, zero Assignment rows, Team Plan copied to project scope, and repeated formal approval returned the same Project ID.
- Frontend production build not run because `frontend/node_modules/.bin/vite` is not present. No frontend files were changed in this release.
- Real Ollama end-to-end planning not run in this environment.
