# Local Agent V2.1 — UI Management and Prompt Foundation

## Conversation management

- Added `DELETE /api/categories/{category_name}`. A deleted category's conversations are preserved and moved to `未分类`.
- Added `DELETE /api/chats/{chat_id}`. The conversation record and its embedded messages are removed from the local chat-history JSON store.
- Added confirmation prompts that explicitly state the operation is permanent and cannot be undone.
- Protected the reserved `未分类` bucket from deletion.

## Chat navigation

- Added a floating scroll-to-latest button when the conversation view is more than 180 px from the bottom.
- `Cmd/Ctrl + ArrowDown` scrolls to the latest message.
- `Cmd/Ctrl + Enter` focuses the composer.
- Plain `Enter` sends; `Shift + Enter` inserts a newline. IME composition is excluded from the send shortcut.

## Prompt architecture

- Added P0 platform safety, P1 system core, P2 role instructions, P3 approved global rules, P4 project context, P5 session context, and P6 current user request layers.
- Added `backend/prompts/prompt_manager.py` for ordered P0–P5 assembly.
- Added a context metadata builder in `backend/context/context_manager.py`.
- Added independent Main Agent and specialist role files.
- Reframed Main Agent as Team Lead; the user remains Product Owner. Hybrid Governance and proposal approval boundaries are explicit.
- P6 is marked on the current user message in the backend request pipeline.
- Full autonomous specialist orchestration and persistent Knowledge Manager lifecycle are not claimed as implemented; role definitions and architecture boundaries are documented.

## Directory cleanup

- Removed `.venv`, `frontend/node_modules`, `.vite`, `.local-agent-run`, Python bytecode caches, `.DS_Store`, and the obsolete `README.txt` patch note from the delivery archive.
- Consolidated Chinese setup instructions into `README_CN.md`.
- Moved architecture, workflow, implementation and historical upgrade notes under `docs/`.
- Preserved `data/local_agent.db` and user data directories; no local database content was intentionally reset.

## Verification

- `python -m compileall -q backend` — passed.
- `python -m unittest backend.test_chat_management backend.test_prompt_manager -v` — 6 tests passed.
- `python -m backend.smoke_test_database` — passed, including 19-table schema, Project/Task, Agent assignment and Proposal approval flows.
- FastAPI HTTP smoke test — category deletion preserves and reclassifies conversations; chat deletion removes the conversation.
- Frontend production build was not verified in this environment: the source archive's macOS-specific native dependency did not match the Linux test runtime, and a clean dependency install timed out. The native `node_modules` directory was excluded from the package; install dependencies on the target Mac using the existing startup script or `npm install` in `frontend/`.
