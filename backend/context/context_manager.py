from __future__ import annotations

from typing import Any


def build_session_context(
    *,
    conversation_id: str,
    model: str,
    context_files: list[str] | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Build bounded P5 metadata; project identity is explicit, never inferred from chat text."""
    return {
        "conversation_id": conversation_id,
        "session_id": session_id or conversation_id,
        "project_id": project_id,
        "model": model,
        "context_file_count": len(context_files or []),
    }


def build_task_context(*, task_id: str | None = None, task_description: str = "", supplied_context: str = "") -> str:
    parts = []
    if task_id:
        parts.append(f"Task ID: {task_id}")
    if task_description.strip():
        parts.append("Task Description:\n" + task_description.strip())
    if supplied_context.strip():
        parts.append("Relevant Context:\n" + supplied_context.strip())
    return "\n\n".join(parts)
