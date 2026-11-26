# Agent Capability and Tool Permission Model — V2.6.1

## Concepts

- **Tool**: a concrete executable operation registered with a backend handler and input schema.
- **Capability**: a business-level unit of work an Agent is allowed to perform. A Capability may grant one or more runtime tool permissions.
- **Direct Tool Assignment**: an additional explicit grant of a concrete configured API Tool or system permission alias.
- **Explicit Deny**: a per-Agent denial that overrides both inherited and direct grants.

## Effective permission calculation

```text
Effective Tools = (Capability Grants ∪ Direct Tool Grants) − Explicit Deny
```

The runtime still applies platform-level workspace-root, database and execution policies. A granted Tool does not bypass those controls.

## Current assignable capabilities

| Capability ID | Grants | Risk |
|---|---|---|
| `data_analysis` | `sqlite_query` | Low |
| `data_cleaning` | `workspace_modify` | Medium |
| `data_export` | `workspace_modify` | Medium |
| `database_modification` | `sqlite_modify` | High |
| `workspace_file_management` | `workspace_modify` | Medium |

`workspace_modify` is a permission alias expanded by Specialist Runtime into supported workspace write/create/move/copy/rename tools. Workspace delete remains unavailable to Specialists.

## Direct Tool Assignment

Configured HTTPS API Tools are assigned by their registered `function_name`. The tool must be enabled in Tool Management before it can be used. System aliases `sqlite_modify` and `workspace_modify` may also be granted directly.

## Compatibility

Historical free-text entries in an Agent's `capabilities` list remain descriptive-only. They are surfaced as Additional descriptive skills in the editor and do not grant runtime permissions. Only registered, assignable Capability IDs are interpreted as permission-bearing capabilities.

## Runtime enforcement

Specialist Runtime resolves the effective permission set before registering tools. It does not register mutating SQLite or workspace tools unless they are in the effective set. Explicit denial also removes default read tools when `sqlite_query`, `workspace_list` or `workspace_read` is denied. Workspace path containment and project access settings remain enforced independently.
