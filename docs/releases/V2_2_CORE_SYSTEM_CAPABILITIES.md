# V2.2 Core System Capabilities Update

## Purpose

This release turns the agreed capability boundaries into Main Agent runtime behavior. It does not add OCR, PDF parsing, image processing, Python execution, Marketplace downloads, or general third-party extension installation.

## Capability policy

### SQLite
- SQLite access is grouped into two operations: Query and Modify.
- `sqlite_query` is read-only and uses SQLite's authorizer to deny writes and schema changes.
- `sqlite_modify` is exposed only when the current Main Agent request clearly indicates a data/schema modification.
- The Modify executor accepts one SQL statement and denies ATTACH/DETACH, PRAGMA and unsupported administrative actions.
- Query results are limited to 500 rows.

### Project management
- Read operations (project list, Agent list, project tasks) are separated from mutation operations.
- Main Agent receives mutation schemas only when the current request indicates a project/task change.
- When dispatching a Specialist from a project-linked conversation, Main Agent attaches a read-only project and task snapshot to the Specialist context.
- Specialist Runtime receives a read-only snapshot of the linked project and its tasks at dispatch. It does not receive project-management mutation tools or a live project-management query interface.

### Web search
- Main Agent can use the configured SerpApi-backed Google Search capability when a request asks for current/web information.
- Search remains dependent on `SERPAPI_API_KEY` in the backend environment in this release.
- Specialist Agents do not receive automatic internet access. Main Agent should pass relevant search findings as task context.

### File management
- Added Main Agent workspace file tools: list, read, write, create directory, copy, move, rename and delete.
- Specialist Agents receive workspace list/read by default; workspace modifications require the explicit `workspace_modify` permission. Specialist delete remains disabled.
- Paths are relative to the configured Project Access root and cannot escape it.
- Hidden/internal state paths, dependency directories, parent traversal and symbolic links are blocked.
- Text/source writes are limited to supported extensions and 2 MB; existing files are backed up before replacement.
- Write tools are exposed only when Project Access write permission is enabled. Delete is intended only for explicit user requests.
- This is not a full binary/document parser. PDF, Word, Excel and image-content extraction are not implemented by these tools.

### Agent profile semantics
- Capabilities are professional-skill descriptions for Main Agent routing; they do not create executable functionality.
- Supported Task Types are routing guidance; they are not security permissions.
- Tool Permissions are stored separately and enforced by Specialist Runtime. SQLite Query and workspace Read are default read-only capabilities; SQLite Modify (`sqlite_modify`) and Workspace Modify (`workspace_modify`) require explicit grants. Enabled API Tools are exposed only when listed in the Agent allow-list.

## Future optional capabilities

OCR, PDF processing, Excel processing, image processing, Python execution and archive management remain optional capabilities. They must have a real implementation, registration and runtime validation before being advertised as available to Agents.

## Marketplace deferral

Third-party code download, package installation and arbitrary extension execution remain deferred. No Marketplace installer is included in this release.

## Verification
- Python compileall completed successfully.
- 27 unit tests passed, including SQLite authorizer checks, file path/symlink confinement, routing detection and read-vs-mutation project management schema checks.
- FastAPI application import and route registration succeeded.
- Frontend production build was not verified because `npm ci` timed out in the current environment; no successful Vite build is claimed.
- No live Ollama, external SerpApi, or user-specific local workspace end-to-end run was performed.

## UI
- Added a System Capabilities page that separates implemented Core capabilities from Optional capabilities that are still planned.
- Agent profile fields now clarify that Capabilities are professional-skill descriptions and Supported Task Types are routing guidance.
- Specialist Tool Permissions now include default SQLite Query and authorised workspace Read, plus opt-in SQLite Modify and Workspace Modify. Registered API Tools can also be explicitly assigned.
- Workspace page file APIs are registered at application startup, now include copy and delete, and reject hidden/internal paths, parent traversal and symlink access.
