# V2.2 Main Agent Intent Router

## Scope

Introduces a first-pass routing layer for Main Agent turns, separating ordinary responses, registered Tool queries, and Specialist Agent delegation.

## Routing modes

| Mode | Capability exposure | Expected behaviour |
|---|---|---|
| `direct_response` | No project, management, database, proposal, or dispatch tools | Answer directly |
| `tool_query` | Only detected registered Tool groups | Execute the required Tool and integrate its result; do not delegate |
| `agent_delegation` | Specialist dispatch | Delegate a bounded specialist task and integrate the returned result |

## Safety and governance

- Routing does not grant project execution authority.
- Existing project execution guard still requires Execution Authorization and an Active P4.
- Project identity continues to come from trusted conversation metadata.
- Tool availability is not Agent availability; Tools and Agents remain distinct.
- The backend remains the source of truth for execution evidence.

## Current limitation

This is a deterministic first-pass classifier using existing request detectors and explicit complexity/delegation cues. It is not yet a model-based intent planner, and ambiguous requests deliberately default to Direct Response. The classifier should be expanded only with test cases demonstrating a real routing failure.
