# V2.2 — Project Context and Prompt Routing

## Project conversations
- A Project detail view can create a new conversation linked to the selected Project ID.
- `chats.json` stores `project_id` and `project_name` per conversation; legacy/global conversations remain unlinked.
- A global conversation is bound only when the user explicitly references exactly one known project. Ambiguous or cross-project references remain global and receive a project catalog in P5 for clarification.

## Project Prompt (P4)
- Formal project creation initializes one project prompt at `AgentWorkspace/.agent_state/project_prompts/<project_id>/project_prompt.md`.
- Prompt versions and metadata are stored alongside the project file.
- Initial and changed prompts enter `pending_review`.
- `project_prompt.md` remains the single canonical P4 file. New drafts and immutable version snapshots are stored separately; runtime continues to use the canonical active file while a newer draft is pending. Product Owner activation atomically replaces the canonical file.
- Main Agent can propose a new version through `propose_project_prompt_update`; it cannot activate the prompt.
- Project workspace provides prompt editing and Product Owner activation controls.

## Runtime prompt composition
- Main Agent and Specialist Agents use the same P0-P6 builder.
- P2 is selected by Agent ID.
- P4 is selected by trusted Project ID.
- P5 contains conversation/session/task metadata.
- P6 is the current user request or Main Agent task instruction.
- Specialist execution in a project requires both execution authorization and an active P4 baseline.

## Validation
- Python compilation passed.
- Existing Prompt Manager tests passed.
- Project Prompt versioning and active-baseline preservation checks passed.
- Project-linked and global conversation persistence checks passed.
- Frontend production build was not run because frontend dependencies were unavailable in the execution environment.
