# V2.2 Specialist Agent Management and Model Routing

## Scope
- Added owner-managed Agent Management API and UI for existing predefined Specialist Agents.
- Added per-agent model selection, enabled/disabled status, capabilities, allowed task types, display name, and P2 role instruction override.
- Persisted configuration in `AgentWorkspace/.agent_state/specialist_agents.json`.
- Main Agent delegation schema now exposes only enabled, registered Specialist Agent IDs and includes configured capability/task metadata.
- Dispatcher rejects disabled agents and uses the configured per-agent model, falling back to the current chat model when no override is set.

## Validation
- Python compile check passed.
- Existing prompt/chat unit tests: 6 passed.
- Agent registry configuration round-trip check passed.
- Frontend production build not run because Vite dependencies are not installed in the environment.
- Real Ollama multi-agent end-to-end execution not tested.

## Limitation
This version configures the existing role-prompt-defined agents. Creating an entirely new agent identity still requires adding a role definition under `backend/prompts/roles/`; the UI does not yet create new agent identities.
