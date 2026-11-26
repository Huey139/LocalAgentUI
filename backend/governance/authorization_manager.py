from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    requires_product_owner_approval: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason,
                "requires_product_owner_approval": self.requires_product_owner_approval}


class AuthorizationManager:
    """Conservative Hybrid Governance gate for project lifecycle actions."""
    RESERVED_ACTIONS = {
        "formal_project_approval": "Formal project creation requires Product Owner approval.",
        "execution_start": "Execution requires explicit execution authorisation.",
        "scope_change_major": "A material scope change requires Product Owner approval.",
        "budget_commitment": "A binding budget commitment requires Product Owner approval.",
        "external_irreversible_action": "An external or irreversible action requires Product Owner approval.",
        "final_acceptance": "Final project acceptance is reserved to the Product Owner.",
    }

    def evaluate(self, action: str, permissions: dict[str, Any] | None = None) -> AuthorizationDecision:
        permissions = permissions or {}
        action = action.strip().lower()
        if action in self.RESERVED_ACTIONS:
            return AuthorizationDecision(False, self.RESERVED_ACTIONS[action], True)
        if action in {"requirement_analysis", "draft_planning", "task_decomposition", "agent_selection_proposal", "risk_analysis"}:
            return AuthorizationDecision(True, "Permitted as planning activity; this does not authorise execution.")
        granted = permissions.get(action) is True
        if granted:
            return AuthorizationDecision(True, "Explicit permission was supplied for this action.")
        return AuthorizationDecision(False, f"No explicit permission was supplied for '{action}'.")
