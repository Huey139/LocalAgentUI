# Architecture-to-Code Map

This map links the documented design areas to the current source tree. It is an orientation aid, not a complete dependency graph.

| Design area | Main source locations |
|---|---|
| Application/API | `backend/main.py`, `backend/*_api.py` |
| Agent runtime and dispatch | `backend/agents/` |
| Capability catalog and permission resolution | `backend/capability_catalog.py`, `backend/governance/` |
| Tool registration and handlers | `backend/tools/` |
| Planning and orchestration | `backend/planning/`, `backend/team_orchestration_api.py` |
| Prompt assembly | `backend/prompts/`, `backend/project_prompts.py` |
| Runtime and session context | `backend/context/` |
| Proposal and Project workflows | `backend/proposal_api.py`, `backend/project_api.py` |
| Workspace and artifacts | `backend/workspace_api.py`, `backend/database.py` |
| Database bootstrap and migrations | `backend/db/` |
| Frontend | `frontend/src/` |

Some legacy or compatibility modules remain in the repository. Do not infer that every similarly named module is active; verify imports and runtime paths before removing or consolidating files.
