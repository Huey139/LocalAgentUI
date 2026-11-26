# V2.4.1 – Proposal Confirmation Card

## Purpose

Make the exact Proposal content being approved visible and unambiguous inside the chat conversation.

## Changes

- Assistant messages for successfully saved Proposals now include a structured `ui_confirmation` payload built from the persisted Proposal record, not from free-form model text.
- The chat renders a visually bounded Proposal Confirmation Card containing the Proposal ID, content snapshot timestamp, objective, scope, deliverables, milestones, timeline, risks, assumptions and priority metadata.
- Team Planning and Formal Project Approval actions are displayed inside the card so the decision controls are visually tied to the reviewed content.
- Formal approval requests include a SHA-256 fingerprint of the reviewed Proposal snapshot.
- Backend recalculates the fingerprint from the current database record before approval. If the Proposal changed after the card was displayed, the action is rejected with HTTP 409 and the user must review the latest content.
- The browser confirmation prompt also names the Proposal and ID. Successful approval still depends on the real Backend lifecycle service response and returned Project ID.
- Formal Project Approval does not grant Execution Authorization.

## Snapshot semantics

This release uses a content fingerprint and the persisted `updated_at` timestamp to bind the approval action to the exact record displayed in the card. It does not yet introduce a formal numeric Proposal version history or a multi-turn Discussion Consolidation workflow; those remain separate lifecycle enhancements.

## Verification

- `python -m compileall -q backend`: passed.
- Existing Backend regression suite: 38 tests passed.
- New Proposal confirmation snapshot tests: 3 tests passed.
- Frontend production build: not run in this packaging environment because frontend dependencies are not installed in the extracted source directory.
