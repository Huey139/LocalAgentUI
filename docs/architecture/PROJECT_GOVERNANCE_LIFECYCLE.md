# Project Governance Lifecycle

## Authority boundaries

| Stage | Lifecycle state | Permitted activity | Not permitted |
|---|---|---|---|
| Proposal discussion | `proposal_submitted` | Clarify and revise Proposal; generate pre-project Team Plan | Project/task creation or Specialist execution |
| Formal Project Approved | `formal_project_approved` | Persist Project row, approved Proposal baseline and proposed Team Plan | Task execution or Agent dispatch |
| Execution Authorised | `execution_authorized` | Begin approved task work when task orchestration is available | Unapproved scope expansion |
| In Progress | `in_progress` | Execute approved tasks and review outputs | Final acceptance by Main Agent |
| Pending Acceptance | `pending_acceptance` | Product Owner review | Further task execution unless returned to in-progress |
| Accepted | `accepted` | Close project | Further lifecycle transitions |
| Rejected | `rejected` | Retain rejection record | Project creation or execution |

`approved_in_principle` and `planning_authorized` remain in the lifecycle enum for compatibility with earlier V2.2 records and commands. The current Proposal-to-Project workflow does not require those intermediate approvals: the Product Owner discusses the Proposal and Team Plan, then gives one explicit formal project confirmation.

## Chat commands

- `plan team for proposal <proposal-id>`
- `formally approve proposal <proposal-id>`
- `reject proposal <proposal-id>`
- `request changes for proposal <proposal-id>: <comment>`
- `authorize execution for project <project-id>` (execution-stage command; task orchestration is deferred)

## API endpoints

- `POST /api/v1/proposals`
- `PATCH /api/v1/proposals/{proposal_id}`
- `POST /api/v1/proposals/{proposal_id}/team-plan/analyze`
- `POST /api/v1/proposals/{proposal_id}/formal-approval`
- `POST /api/v1/projects/{project_id}/authorize-execution`
- `POST /api/v1/projects/{project_id}/submit-for-acceptance`
- `POST /api/v1/projects/{project_id}/accept`

The lifecycle state is persisted in `sys_project_lifecycle`. Proposal review status remains separate. Formal approval writes `sys_projects` and links the Project ID to the Proposal. It does not create task or assignment records in this release.
