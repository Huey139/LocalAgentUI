from __future__ import annotations

from enum import Enum


class ProjectLifecycle(str, Enum):
    PROPOSAL_SUBMITTED = "proposal_submitted"
    APPROVED_IN_PRINCIPLE = "approved_in_principle"
    PLANNING_AUTHORIZED = "planning_authorized"
    FORMAL_PROJECT_APPROVED = "formal_project_approved"
    EXECUTION_AUTHORIZED = "execution_authorized"
    IN_PROGRESS = "in_progress"
    PENDING_ACCEPTANCE = "pending_acceptance"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ApprovalManager:
    """Defines legal lifecycle transitions; persistence is owned by API services."""
    TRANSITIONS = {
        ProjectLifecycle.PROPOSAL_SUBMITTED: {ProjectLifecycle.APPROVED_IN_PRINCIPLE, ProjectLifecycle.FORMAL_PROJECT_APPROVED, ProjectLifecycle.REJECTED},
        ProjectLifecycle.APPROVED_IN_PRINCIPLE: {ProjectLifecycle.PLANNING_AUTHORIZED, ProjectLifecycle.REJECTED},
        ProjectLifecycle.PLANNING_AUTHORIZED: {ProjectLifecycle.FORMAL_PROJECT_APPROVED, ProjectLifecycle.REJECTED},
        ProjectLifecycle.FORMAL_PROJECT_APPROVED: {ProjectLifecycle.EXECUTION_AUTHORIZED},
        ProjectLifecycle.EXECUTION_AUTHORIZED: {ProjectLifecycle.IN_PROGRESS},
        ProjectLifecycle.IN_PROGRESS: {ProjectLifecycle.PENDING_ACCEPTANCE},
        ProjectLifecycle.PENDING_ACCEPTANCE: {ProjectLifecycle.ACCEPTED, ProjectLifecycle.IN_PROGRESS},
        ProjectLifecycle.ACCEPTED: set(),
        ProjectLifecycle.REJECTED: set(),
    }

    @classmethod
    def can_transition(cls, current: ProjectLifecycle | str, target: ProjectLifecycle | str) -> bool:
        try:
            source = ProjectLifecycle(current)
            destination = ProjectLifecycle(target)
        except ValueError:
            return False
        return destination in cls.TRANSITIONS[source]

    @classmethod
    def validate_transition(cls, current: ProjectLifecycle | str, target: ProjectLifecycle | str) -> None:
        if not cls.can_transition(current, target):
            raise ValueError(f"Invalid project lifecycle transition: {current} -> {target}")
