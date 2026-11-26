# V2.2 — LLM Project Team Planning

## Scope

This increment replaces keyword-only team matching with a planning request to the configured Main Agent Ollama model. The planner receives the project objective and description, the Product Owner-approved active P4 only, existing project tasks, enabled Specialist Agent profiles, the system capability catalog, registered Tool metadata, and installed Ollama model names.

The LLM returns structured JSON describing a project summary, proposed workstreams, required capabilities and Tools, candidate Agent IDs, rationale, confidence, risks, assumptions, and questions for the Product Owner.

## Deterministic validation

The backend validates the LLM proposal against current local configuration:

- Candidate Agent IDs must exist and be enabled.
- Each proposed Agent model must be configured and present in the installed Ollama model list.
- Requested capabilities must exist in the system capability catalog and be available.
- Requested Tools must exist in the built-in/configured Tool catalog and be enabled.
- Requested Tools must also be present in each candidate Agent's explicit `allowed_tools` permission list.
- Unknown Agent, capability, Tool, disabled Tool, unavailable model, and missing permission conditions become capability/configuration gap requests.

LLM output is schema-validated. Invalid output or an unavailable Ollama service returns an API error; the backend does not silently claim a heuristic plan is an LLM plan.

## Governance boundary

The result remains a `draft`. It does not create project tasks, persist a formal Agent assignment, dispatch Specialists, or grant execution authorization. Product Owner approval remains separate from project execution authorization. Approval is blocked while configuration gaps remain or proposed candidates are not ready. After changing Agent, Tool, or model configuration, regenerate the plan to refresh deterministic validation.

## P4 handling

The planning service reads only the active, Product Owner-approved P4 version. A pending draft is deliberately excluded, even though the Project Prompt editor API returns that draft for editing.

## Known limitations

- The LLM planning response is a recommendation, not proof that an Agent can successfully complete a task.
- Candidate matching quality depends on the accuracy of Agent capability declarations and role descriptions.
- Capability availability is checked against the system capability catalog; deeper runtime-specific preconditions may still need dedicated validators.
- The plan is stored in the existing JSON state file and is not yet a normalized database assignment record.
- No real Ollama end-to-end call or frontend production build was performed in the development environment.
