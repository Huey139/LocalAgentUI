from __future__ import annotations

from typing import Any


class ProjectPlanner:
    """Normalises a planning brief into reviewable workstreams and dependency metadata."""
    REQUIRED_SECTIONS = ("objective", "scope", "deliverables", "acceptance_criteria", "risks", "assumptions")

    def build_plan(self, brief: dict[str, Any]) -> dict[str, Any]:
        missing = [key for key in self.REQUIRED_SECTIONS if key not in brief]
        workstreams = brief.get("workstreams", [])
        tasks = brief.get("tasks", [])
        if not isinstance(workstreams, list) or not isinstance(tasks, list):
            raise ValueError("workstreams and tasks must be lists")
        task_ids = {str(task.get("task_id")) for task in tasks if isinstance(task, dict) and task.get("task_id")}
        dependency_errors = []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            for dependency in task.get("depends_on", []) or []:
                if str(dependency) not in task_ids:
                    dependency_errors.append({"task_id": task.get("task_id"), "missing_dependency": dependency})
        return {
            "ready_for_review": not missing and not dependency_errors,
            "missing_sections": missing,
            "dependency_errors": dependency_errors,
            "workstreams": workstreams,
            "tasks": tasks,
            "budget_status": "estimate_only_unless_supported_by_cost_evidence",
            "timeline_status": "proposed_duration_not_committed_date",
        }
