# Changelog

## Unreleased — GitHub preparation

- Reworked English and Chinese README files to describe the project's vision, experimental status, requirements and documentation entry points.
- Added installation, configuration and troubleshooting guides based on the current macOS launch scripts and dependency manifests.
- Added Mermaid architecture documentation for system layers, AI organisation, project workflow, permissions, prompt/context and workspaces/artifacts.
- Added contribution, security, code-of-conduct and roadmap documents.
- Strengthened Git ignore rules for local databases, runtime files, workspace contents and generated artifacts.
- Removed local runtime state and installed dependency directories from the distributable source archive; these are recreated during setup.

## 2.6.1 — Agent Capability & Tool Permission Separation

- Separated Agent Capability assignments from direct Tool assignments in Agent Management.
- Added a capability-to-tool grant catalog for implemented Specialist capabilities.
- Added effective permission resolution: inherited capability tools plus direct tools, minus explicit denials.
- Applied resolved permissions to Specialist Runtime tool registration.
- Added explicit Deny support for registered API tools and system tools.
- Kept legacy free-text capability labels as descriptive-only notes; they do not grant execution permissions.
- Updated the Capabilities page to show assignability, risk level and granted tools.
- Added regression tests for permission inheritance, direct grants, deny precedence and runtime enforcement.

## 2.6.0 — Unified Context, Workspace & Artifact Management

- Added persisted per-Chat Business Context and APIs to bind Proposal/Project/task context.
- Main Agent receives persisted Business Context from SQLite as runtime context.
- Added Temporary, Project and Global Workspace records and managed directory creation.
- Added Artifact Registry with file checks, SHA-256 checksums, workspace path-containment validation and status transitions.
- Added execution evidence records for context binding and artifact registration.
- Added SQLite schema migration v004; previous migrations remain immutable.

See `docs/releases/` for historical implementation notes. Historical notes may describe intermediate states and are not a substitute for checking current source code.
