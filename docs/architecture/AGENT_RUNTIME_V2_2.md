# Agent Runtime Architecture — V2.2

## Entity model
- **Main Agent:** Team Lead responsible for orchestration and integration.
- **Specialist Agent:** registered role identity with its own role instruction file.
- **Tool:** callable capability registered with ToolManager. A tool is not an Agent.
- **Agent Runtime:** executes a selected specialist role as an isolated model call.
- **Agent Dispatcher:** validates the requested specialist and routes the assignment.
- **Agent Result Manager:** creates a dispatch record for returned results.

## Dispatch sequence
1. Main Agent receives a user request.
2. Main Agent chooses a registered specialist and creates a bounded task.
3. `delegate_to_specialist` is emitted as a model tool call.
4. Backend validates the call and invokes AgentDispatcher.
5. AgentRegistry resolves the role prompt.
6. AgentRuntime calls the configured local model with the specialist role and supplied context.
7. AgentResultManager records the result.
8. Result is returned to Main Agent for review and integration.

## Capability boundary
V2.2 specialist runtime is isolated and text-only. It does not inherit project tools or database tools. This prevents accidental privilege inheritance. A later capability grant layer must explicitly define read/write scopes, allowed tools, and approval requirements before specialist access is expanded.

## Governance boundary
Planning and task decomposition may proceed within the user's request. Formal project approval, execution authorisation, material scope changes, binding budget commitments, irreversible external actions, and final acceptance remain Product Owner decisions. The current governance classes define policy primitives; API/database enforcement is a subsequent integration step.


## Unified P0-P6 runtime prompt

Main Agent and Specialist Agents now use `assemble_runtime_prompt()` in `backend/prompts/prompt_manager.py`. The selected Agent ID determines P2; trusted conversation/project metadata determines P4; session and task metadata populate P5; the current user/task instruction is P6. Specialist Agent execution receives the same Project Prompt file as Main Agent.

## Project entry and conversation association

Project detail pages can open a new Project-linked conversation. The chat record stores `project_id`; global chats retain `null`. A global chat can be bound when the user explicitly names exactly one known project. Ambiguous references remain unbound and the project catalog is supplied in P5 for clarification.

## Main Agent Intent Routing

The Main Agent now performs a deterministic first-pass intent classification before constructing the model's available tool schemas. The routing modes are:

- `direct_response`: no registered Tool operation or Specialist dispatch is exposed; the Main Agent answers from the conversation and loaded prompt context.
- `tool_query`: only the detected Tool capability groups are exposed (project files, proposal, management, or database schema). Specialist dispatch is not exposed for this mode.
- `agent_delegation`: the Specialist dispatch capability is exposed for explicit delegation requests or requests that combine substantial technical work with a specialist-oriented outcome.

The router is a capability gate, not an execution engine or an authority grant. Existing backend handlers remain responsible for tool execution, project identity, execution authorization, and Project Prompt checks. Ambiguous requests default to `direct_response`; a Tool or Agent must never be claimed as executed unless the backend returns evidence.

## Specialist Agent Management and model assignment

Specialist identities remain predefined by role prompt files under `backend/prompts/roles/`. The Agent Management API and UI configure those existing identities without allowing Main Agent to invent agent IDs or model assignments.

Owner-managed configuration is stored locally at `AgentWorkspace/.agent_state/specialist_agents.json` and includes display name, model override, capabilities, allowed task types, enabled status, and optional P2 role-prompt override. If an agent model is blank, dispatch uses the current chat model. Disabled agents are excluded from the delegation schema and are rejected by the dispatcher as a second guard. The dispatcher resolves the model from the selected agent configuration rather than accepting a model choice from Main Agent.

Endpoints:
- `GET /api/agents`
- `PUT /api/agents`

The Main Agent receives the enabled agent IDs and their configured capability/task descriptions when delegation is available. The registry remains the source of valid agent identities.
