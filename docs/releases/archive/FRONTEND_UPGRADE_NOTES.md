# Local Agent – Frontend Structure Upgrade (Prototype)

## Changes
- Renamed the product UI to **Local Agent**.
- Added primary navigation: Projects & Tasks, Chat & Inquiry, Workspace, Settings.
- Set Projects & Tasks as the default landing page.
- Added a project workflow dashboard prototype with five stages, a current-task summary and Agent activity.
- Moved model selection and project access controls into Settings.
- Kept the existing chat API integration, conversation history, categories, context handling and message sending.
- Moved file browsing and management into the dedicated Workspace page; Workspace file checkboxes can still be selected as chat context.
- Added responsive layout rules for narrower screens.

## Important limitations
- The Dashboard currently uses clearly labelled static prototype data. It is not connected to Project, Task or Agent management APIs because those backend modules do not exist in the supplied initial version.
- New Project is intentionally disabled until the Project API is implemented.
- The existing backend has not been modified.
- The original source archive contained macOS-specific `node_modules`. Those dependencies are excluded from this upgraded archive. Run `npm install` in `frontend/` on the target Mac before starting the app.

## Run
```bash
cd frontend
npm install
npm run dev
```

The existing backend should be started separately using its current instructions.


## Main Agent behaviour update — V1.1

- Repositioned the system prompt from a coding assistant to a general-purpose Main Agent.
- Ordinary Q&A no longer receives project-file tool definitions, reducing accidental file-tool calls by small local models.
- Project tools are exposed only when the user message indicates a project/file/code operation.
- Prompt now states current capability boundaries: project/task database, specialist-agent workforce, and task orchestration are not yet implemented.
- File-operation activity is presented as concise human-readable execution records rather than raw tool names and file contents.
- Chat loading and composer wording now describe Main Agent behaviour.
- Updated macOS startup instructions to use `npm install` and `npm run dev`, with backend and frontend in separate terminals.
