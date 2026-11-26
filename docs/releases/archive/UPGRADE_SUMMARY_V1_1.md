# Local Agent V1.1 — Main Agent & Chat Behaviour Update

## Changes

### Backend
- Replaced the coding-assistant-only system prompt with a Main Agent role focused on natural conversation, intent understanding, and truthful reporting.
- Added project-tool intent gating. Project file tools are only included in the Ollama request when the latest user message clearly combines a project/code/file reference with an operation request.
- Ordinary Q&A no longer receives project file tool definitions. This is intended to reduce accidental calls from small local models.
- Explicitly documented current capability limits in the prompt: Project/Task persistence, specialist agents, and task orchestration are not implemented yet.
- Replaced raw tool-name activity strings with concise user-facing execution descriptions.

### Frontend
- Updated Chat welcome text and composer placeholder to position the assistant as Main Agent.
- Updated the busy indicator to show that Main Agent is processing the request.
- Changed the context panel role label to Main Agent.
- Replaced the raw `文件操作：list_project_files...` presentation with a concise `执行记录` display.
- Added compatibility formatting for old conversation records that contain raw tool names.

### Documentation
- Updated macOS run instructions to use `npm install` and `npm run dev` in the frontend directory, with the backend running in a separate Terminal window.

## Validation
- `backend/main.py` passed Python bytecode compilation (`python -m py_compile`).
- Intent-gating checks passed for ordinary greetings/general knowledge and explicit project/code/file operations.
- Frontend production build was not verified in this Linux environment. Dependency installation did not complete within the available execution window; run `npm install` and `npm run dev` on the target Mac to validate there.

## Not included yet
- SQLite Project/Task/Agent database and APIs.
- Specialist Agent runtime and orchestration.
- Real task queue, execution sessions, retries, QA workflow, approval workflow, and live progress events.
- Real project-backed Dashboard data.
