# V2.2 Ollama Model Discovery Fix

## Changes
- Decoupled Ollama model discovery (`GET /api/models`) from the other application startup requests. A failure loading chats, files, categories, or project settings no longer prevents the Agent Management model selectors from receiving the installed model list.
- Added model loading and error states to Agent Management.
- Added a manual **Refresh models** action so newly installed Ollama models can be discovered without restarting the UI.
- Displays the backend error and a practical connectivity hint when Ollama model discovery fails, rather than leaving the selector silently empty.
- Preserves the selected model when it remains installed; otherwise selects the configured default when available, then the first installed model.

## Verification
- `python -m compileall -q backend` passed.
- `python -m unittest backend.test_prompt_manager backend.test_chat_management backend.test_tool_registry -v` passed (10 tests).
- Frontend production build was not run because frontend dependencies are not installed in this environment.
- Live Ollama discovery was not tested against the user's Mac service.
