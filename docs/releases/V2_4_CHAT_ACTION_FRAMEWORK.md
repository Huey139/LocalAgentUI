# V2.4 – Interactive Chat Action Framework (Foundation)

## Purpose

Introduce structured, clickable actions inside chat messages so the Product Owner can trigger supported lifecycle operations without copying command text into the composer.

## Implemented in this foundation

- Assistant messages may include a structured `ui_actions` array.
- The chat frontend renders those actions as buttons.
- Buttons call `POST /api/chats/{chat_id}/actions` rather than submitting an ordinary chat prompt.
- The backend exposes an explicit action allowlist:
  - `proposal.team_plan`
  - `proposal.formal_approve`
- Actions require a valid Proposal ID associated with the active conversation.
- Formal Project Approval requires a second confirmation in the UI.
- The backend performs the real lifecycle operation and returns the updated chat only after the service call succeeds.
- Formal approval links the newly created Project to the current chat and returns the actual Project ID.
- Team Planning remains separate from Formal Project Approval. Formal approval does not grant Execution Authorization.

## Message contract

An assistant message may contain:

```json
{
  "role": "assistant",
  "content": "Proposal saved...",
  "ui_actions": [
    {
      "type": "proposal.team_plan",
      "label": "Start Team Planning",
      "proposal_id": "<backend-generated-proposal-id>"
    },
    {
      "type": "proposal.formal_approve",
      "label": "Formal Project Approval",
      "proposal_id": "<backend-generated-proposal-id>"
    }
  ]
}
```

The frontend treats the message contract as presentation data only. It does not execute arbitrary model-provided URLs, code, or endpoint names. The backend independently validates the action type and Proposal association.

## API

`POST /api/chats/{chat_id}/actions`

Request:

```json
{
  "action": "proposal.formal_approve",
  "proposal_id": "<proposal-id>"
}
```

Only the two allowlisted action types are accepted. Formal approval uses the existing lifecycle service. Team Planning uses the existing Proposal Team Plan service.

## Current limitations

- This is the first interactive-action slice, not a complete generic form/card framework.
- Only Proposal Team Planning and Formal Project Approval are wired to real actions.
- Forms, selection controls, Task Planning actions, execution authorization cards, and generic action versioning are not included yet.
- Frontend production build could not be verified in this Linux packaging environment because the supplied `node_modules` lacks the platform-specific Rolldown native binding. No dependency reinstall or lockfile change was made.
- Backend compile and the existing 38-test regression suite passed.
