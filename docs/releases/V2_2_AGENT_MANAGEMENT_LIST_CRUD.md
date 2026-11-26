# V2.2 Agent Management List & CRUD Update

## Scope

- Reworked Agent Management into a list-first interface consistent with Tool Management.
- Added a protected, predefined Main Agent entry with an independent Ollama model selector.
- Added create, read, update and delete support for custom Specialist Agents.
- Kept predefined Specialist Agent identities backed by `backend/prompts/roles/*.md`; they can be edited and enabled/disabled but cannot be deleted in the UI.
- Added system-generated IDs for custom Agents (`agent_<random>`), plus persisted category, description, role instructions, capabilities, task types, Tool permissions, model and status.
- Added model selection from the installed Ollama model list. Agent creation/update requires a selected model.
- Main Agent model is stored separately in `.agent_state/main_agent_config.json` and is used for subsequent Main Agent chat requests.

## API

- `GET /api/agents` returns `main_agent` configuration and Specialist Agent definitions.
- `PUT /api/agents/main` updates the Main Agent model.
- `POST /api/agents` creates a custom Specialist Agent.
- `PUT /api/agents/{agent_id}` updates a custom or predefined Specialist Agent.
- `DELETE /api/agents/{agent_id}` deletes custom Agents only. Predefined Agents are protected.
- Existing `PUT /api/agents` bulk configuration endpoint remains for compatibility.

## Storage

Custom Agent definitions remain in `.agent_state/specialist_agents.json` under `__custom_agents__`. Main Agent model configuration is stored in `.agent_state/main_agent_config.json`. No database schema migration is required.

## Limitations

- New Agent identities require a Role Instructions (P2) definition, supplied through the UI.
- The Main Agent role instructions remain system-defined; this UI exposes its model setting only.
- The selected Main Agent model is used for subsequent chat turns. Existing Specialist Agent model selection remains independent.
- Marketplace installation and third-party code execution remain deferred.
