# Prompt Architecture

## Layer order

| Layer | File / source | Purpose |
|---|---|---|
| P0 | `backend/prompts/system/p0_platform_safety.md` | Safety, trust boundaries, permissions and truthfulness constraints |
| P1 | `backend/prompts/system/p1_system_core.md` | Product identity and operating principles |
| P2 | `backend/prompts/roles/*.md` | Main Agent and specialist role instructions; selected by `agent_id` |
| P3 | `backend/prompts/global_rules/approved_global_rules.md` | Explicitly approved cross-project rules |
| P4 | `AgentWorkspace/.agent_state/project_prompts/<project_id>/project_prompt.md` | One project-specific instruction file, shared by all agents and conversations associated with that project |
| P5 | Runtime context | Conversation ID, session metadata, project metadata, task context and bounded history |
| P6 | Current instruction | User request for Main Agent, or Main Agent task instruction for a Specialist Agent |

## Runtime composition

Every model call uses the same P0-P6 assembly framework:
- Main Agent: P2 loads `main_agent.md`; P6 is the current user request.
- Specialist Agent: P2 loads the target agent's role; P6 is the task instruction assigned by Main Agent.
- P4 is selected only by a trusted `project_id`. It is never inferred from conversation title or recent activity.
- P0, P1, P3 are shared. P2 varies by agent. P4 is shared within a project. P5 and P6 vary by session and task.
- A global conversation has no P4 unless a single explicit project reference is resolved and the backend binds that conversation to the project.
- Cross-project requests remain global; the Main Agent must not silently select one project's P4.

## Project Prompt lifecycle

A formal project receives exactly one current `project_prompt.md`, keyed by Project ID. Version snapshots and metadata are stored alongside it. The initial prompt is generated as `pending_review`; the Product Owner must activate it before it becomes the approved P4 baseline. Editing creates a new version in `pending_review`; the previous version remains in version history.

## Conversation routing

- Global Main Agent conversations have `project_id = null`.
- Conversations opened from a Project workspace store that project's `project_id`.
- A Project can have multiple conversations; each conversation is associated with at most one Project.
- A global conversation that explicitly names exactly one known project may be bound to it by the backend. Ambiguous or multi-project references remain global.
- Conversation categories are organizational labels only; they do not determine project identity.

## Governance

The user is the Product Owner. The Main Agent is Team Lead. Hybrid Governance means autonomous execution is limited to the permissions and scope already granted; material, irreversible, external-impacting or user-reserved decisions require user approval. The Main Agent cannot approve its own project proposals.
Specialist execution in a project requires both explicit project execution authorization and an Active P4 Project Prompt.

## Knowledge lifecycle boundary

Project-specific observations remain project-scoped. They must be captured, classified, validated and explicitly approved before promotion to approved global rules. Project Prompt, Project Knowledge and transient Context remain separate.

## Implementation boundary

The shared Prompt Builder is used by Main Agent and Specialist Agent Runtime. Agent identity is loaded from Agent Registry; Tool capability is supplied separately by Tool Manager. Project Prompt files do not grant filesystem, database or execution permissions.
