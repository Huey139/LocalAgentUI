from __future__ import annotations

from pathlib import Path
from typing import Any

from ..project_prompts import load_project_prompt
from ..context.runtime_environment import format_runtime_environment

PROMPT_ROOT = Path(__file__).resolve().parent


def _read(relative_path: str, *, required: bool = True) -> str:
    path = PROMPT_ROOT / relative_path
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        if required:
            raise RuntimeError(f"Required prompt file is missing: {relative_path}") from exc
        return ""
    if required and not content:
        raise RuntimeError(f"Required prompt file is empty: {relative_path}")
    return content


def _safe_text(value: Any, default: str = "not supplied") -> str:
    if value is None:
        return default
    return str(value).strip() or default


def assemble_runtime_prompt(
    *,
    agent_id: str,
    agent_role_prompt: str | None = None,
    project_id: str | None = None,
    session_context: dict[str, Any] | None = None,
    task_context: str | None = None,
    current_instruction: str | None = None,
    agent_catalog: list[dict[str, str]] | None = None,
    project_catalog: list[dict[str, str]] | None = None,
    runtime_environment: dict[str, Any] | None = None,
) -> str:
    """Build the canonical P0-P6 prompt for Main Agent or a Specialist Agent."""
    session_context = session_context or {}
    p0 = _read("system/p0_platform_safety.md")
    p1 = _read("system/p1_system_core.md")

    if agent_role_prompt is None:
        role_path = "roles/main_agent.md" if agent_id == "main_agent" else f"roles/{agent_id}.md"
        agent_role_prompt = _read(role_path)

    p3 = _read("global_rules/approved_global_rules.md", required=False)
    if not p3:
        p3 = "# P3 — Approved Global Rules\nNo approved global rules are currently published."

    try:
        p4, project_meta = load_project_prompt(project_id)
    except FileNotFoundError as exc:
        raise RuntimeError(str(exc)) from exc
    if not project_id:
        p4 = "# P4 — Project Instructions\nThis request is not associated with a project."
        project_meta = {"project_id": None, "status": "not_applicable", "version": 0}

    p5_lines = [
        "# P5 — Session and Task Context",
        f"Conversation ID: {_safe_text(session_context.get('conversation_id'))}",
        f"Session ID: {_safe_text(session_context.get('session_id'), 'not supplied')}",
        f"Project ID: {_safe_text(project_id, 'none')}",
        f"Model: {_safe_text(session_context.get('model'), 'runtime-selected')}",
        f"Context files supplied: {session_context.get('context_file_count', 0)}",
        f"Project root: {_safe_text(session_context.get('project_root'))}",
        f"Read access: {'enabled' if session_context.get('read_enabled') is True else 'disabled'}",
        f"Write access: {'enabled' if session_context.get('write_enabled') is True else 'disabled'}",
        f"Project Prompt status: {project_meta.get('status', 'unknown')}",
        f"Project Prompt version: {project_meta.get('version', 0)}",
    ]
    if task_context and task_context.strip():
        p5_lines.extend(["", "## Task Context", task_context.strip()])
    if agent_catalog is not None and agent_id == "main_agent":
        p5_lines.extend(["", "Registered specialist agents (registry identities, not tools):"])
        p5_lines.extend(f"- {item['agent_id']}: {item['display_name']}" for item in agent_catalog)
    if project_catalog is not None and agent_id == "main_agent":
        p5_lines.extend(["", "Available formal projects (reference catalog only; a global conversation is not automatically bound to any project):"])
        p5_lines.extend(
            f"- {item['id']}: {item['name']} [status={item.get('status', 'unknown')}]"
            for item in project_catalog
        )
        p5_lines.append("If the user's project reference is ambiguous, ask which project they mean. Do not infer project identity from recency.")
    p5_lines.append("Do not claim an Agent was dispatched or a Tool executed unless the runtime confirms it.")
    p5 = "\n".join(p5_lines)

    p6 = "# P6 — Current User Request / Task Instruction\n" + (current_instruction or "").strip()
    p0_5 = format_runtime_environment(runtime_environment) if runtime_environment else (
        "# P0.5 — Verified Runtime Environment Context\nNo runtime environment snapshot was supplied for this invocation. "
        "Do not guess technical environment details or capability availability."
    )
    layers = [p0, p0_5, p1, "# P2 — Agent Role Instructions\n" + agent_role_prompt.strip(), p3, p4, p5]
    if current_instruction is not None:
        layers.append(p6)
    return "\n\n---\n\n".join(layer for layer in layers if layer.strip())


def assemble_main_agent_prompt(
    *,
    project_context: dict[str, Any] | None = None,
    session_context: dict[str, Any] | None = None,
    user_request: str | None = None,
    agent_catalog: list[dict[str, str]] | None = None,
    project_id: str | None = None,
    project_catalog: list[dict[str, str]] | None = None,
    runtime_environment: dict[str, Any] | None = None,
) -> str:
    """Backward-compatible Main Agent wrapper around the canonical P0-P6 builder."""
    project_context = project_context or {}
    session_context = session_context or {}
    return assemble_runtime_prompt(
        agent_id="main_agent",
        project_id=project_id,
        session_context={
            **session_context,
            "conversation_id": session_context.get("conversation_id", session_context.get("chat_id")),
            "project_root": project_context.get("project_root"),
            "read_enabled": project_context.get("read_enabled"),
            "write_enabled": project_context.get("write_enabled"),
        },
        current_instruction=user_request,
        agent_catalog=agent_catalog,
        project_catalog=project_catalog,
        runtime_environment=runtime_environment,
    )
