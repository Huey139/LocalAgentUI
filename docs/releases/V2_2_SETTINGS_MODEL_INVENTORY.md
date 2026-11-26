# V2.2 Settings: Installed Model Inventory

## Change
- Replaced the global `Active model` selector in Settings with a read-only inventory of locally installed Ollama models.
- Added a refresh action and retained model-discovery error/loading feedback.
- Clarified that model assignment is managed in Agent Management, independently for Main Agent and Specialist Agents.
- Removed the obsolete frontend `local-agent-model` localStorage selection and its Settings write path.

## Behaviour
- Settings displays all models returned by the existing `/api/models` endpoint.
- The list does not activate, deactivate, or assign a model.
- Agent Management remains the place to select the Main Agent execution model and each Specialist Agent execution model.

## Validation
- Python backend compile check passed (no backend changes in this release).
- Frontend production build was not run because frontend dependencies are not installed in this environment.
- Manual browser/Ollama verification remains outstanding.
