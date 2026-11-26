from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKSPACE = Path(os.getenv("AGENT_WORKSPACE", str(Path.home() / "AgentWorkspace"))).expanduser().resolve()
PROMPT_ROOT = WORKSPACE / ".agent_state" / "project_prompts"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_dir(project_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", project_id or ""):
        raise ValueError("Invalid project_id.")
    return PROMPT_ROOT / project_id


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".prompt-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _metadata_path(project_id: str) -> Path:
    return _project_dir(project_id) / "metadata.json"


def _prompt_path(project_id: str) -> Path:
    return _project_dir(project_id) / "project_prompt.md"


def _read_metadata(project_id: str) -> dict[str, Any]:
    path = _metadata_path(project_id)
    if not path.exists():
        return {"project_id": project_id, "status": "missing", "version": 0, "versions": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"project_id": project_id, "status": "error", "version": 0, "versions": []}
    except (OSError, json.JSONDecodeError):
        return {"project_id": project_id, "status": "error", "version": 0, "versions": []}


def initialise_project_prompt(project_id: str, project: dict[str, Any], proposal_baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create one project-scoped prompt file; initial version awaits Product Owner review."""
    prompt_path = _prompt_path(project_id)
    if prompt_path.exists():
        return get_project_prompt(project_id)

    baseline = proposal_baseline or {}

    def decode_value(key: str, default: Any) -> Any:
        value = baseline.get(key, default)
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return default
        return value

    scope = decode_value("scope_json", {})
    deliverables = decode_value("deliverables_json", [])
    milestones = decode_value("milestones_json", [])
    tasks = decode_value("tasks_json", [])
    risks = decode_value("risks_json", [])
    assumptions = decode_value("assumptions_json", [])

    content = f"""# Project Instructions

## Project Identity
- Project ID: {project_id}
- Project Name: {project.get('name', 'Untitled Project')}
- Objective: {project.get('objective', '')}

## Project Scope
{json.dumps(scope, ensure_ascii=False, indent=2) if scope else 'Scope details have not yet been defined.'}

## Deliverables
{json.dumps(deliverables, ensure_ascii=False, indent=2) if deliverables else 'No deliverables recorded.'}

## Milestones
{json.dumps(milestones, ensure_ascii=False, indent=2) if milestones else 'No milestones recorded.'}

## Planned Work
{json.dumps(tasks, ensure_ascii=False, indent=2) if tasks else 'No task plan recorded.'}

## Risks
{json.dumps(risks, ensure_ascii=False, indent=2) if risks else 'No risks recorded.'}

## Assumptions
{json.dumps(assumptions, ensure_ascii=False, indent=2) if assumptions else 'No assumptions recorded.'}

## Project-wide Instructions
- All agents working on this project must follow this project prompt.
- Do not silently change approved scope, deliverables, budget, timeline, or acceptance criteria.
- Escalate material changes to the Product Owner.
- Keep project-specific knowledge separate from these instructions.
"""
    _atomic_write(prompt_path, content.strip() + "\n")
    metadata = {
        "project_id": project_id,
        "status": "pending_review",
        "version": 1,
        "active_version": None,
        "created_at": _now(),
        "updated_at": _now(),
        "approved_at": None,
        "versions": [{"version": 1, "status": "pending_review", "created_at": _now(), "change_summary": "Initial prompt generated from formally approved proposal."}],
    }
    _atomic_write(_metadata_path(project_id), json.dumps(metadata, ensure_ascii=False, indent=2))
    version_dir = _project_dir(project_id) / "versions"
    version_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(version_dir / "v0001.md", content.strip() + "\n")
    return get_project_prompt(project_id)


def get_project_prompt(project_id: str) -> dict[str, Any]:
    path = _prompt_path(project_id)
    metadata = _read_metadata(project_id)
    if not path.is_file():
        return {"project_id": project_id, "status": "missing", "version": 0, "content": ""}
    content = path.read_text(encoding="utf-8")
    # If an active baseline exists, return the pending draft to the Project Prompt editor.
    if metadata.get("status") == "pending_review" and metadata.get("active_version"):
        candidate_version = int(metadata.get("version", 0))
        draft_path = _project_dir(project_id) / "drafts" / f"v{candidate_version:04d}.md"
        if draft_path.is_file():
            content = draft_path.read_text(encoding="utf-8")
    return {**metadata, "content": content}


def update_project_prompt(project_id: str, content: str, change_summary: str) -> dict[str, Any]:
    if not content.strip():
        raise ValueError("Project prompt content cannot be empty.")
    current = get_project_prompt(project_id)
    if current["status"] == "missing":
        raise FileNotFoundError("Project prompt has not been initialised.")
    next_version = int(current.get("version", 0)) + 1
    clean_content = content.strip() + "\\n"
    version_dir = _project_dir(project_id) / "versions"
    version_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(version_dir / f"v{next_version:04d}.md", clean_content)

    metadata = {k: v for k, v in current.items() if k != "content"}
    has_active_baseline = bool(metadata.get("active_version"))
    if has_active_baseline:
        # Keep the single canonical project_prompt.md unchanged until Product Owner activation.
        draft_dir = _project_dir(project_id) / "drafts"
        draft_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(draft_dir / f"v{next_version:04d}.md", clean_content)
    else:
        _atomic_write(_prompt_path(project_id), clean_content)

    metadata.update({
        "version": next_version,
        "status": "pending_review",
        "updated_at": _now(),
        "approved_at": None,
        "versions": list(current.get("versions", [])) + [{
            "version": next_version, "status": "pending_review", "created_at": _now(),
            "change_summary": change_summary.strip() or "Project prompt updated."
        }],
    })
    _atomic_write(_metadata_path(project_id), json.dumps(metadata, ensure_ascii=False, indent=2))
    return get_project_prompt(project_id)


def activate_project_prompt(project_id: str) -> dict[str, Any]:
    current = get_project_prompt(project_id)
    if current["status"] == "missing":
        raise FileNotFoundError("Project prompt has not been initialised.")
    candidate_content = current.get("content", "").strip() + "\\n"
    # project_prompt.md is the single canonical P4 file; activation atomically replaces it.
    _atomic_write(_prompt_path(project_id), candidate_content)
    metadata = {k: v for k, v in current.items() if k != "content"}
    metadata["status"] = "active"
    metadata["active_version"] = metadata.get("version", 0)
    metadata["approved_at"] = _now()
    metadata["updated_at"] = _now()
    versions = list(metadata.get("versions", []))
    for item in versions:
        if item.get("version") == metadata["active_version"]:
            item["status"] = "active"
            item["approved_at"] = metadata["approved_at"]
    metadata["versions"] = versions
    _atomic_write(_metadata_path(project_id), json.dumps(metadata, ensure_ascii=False, indent=2))
    return get_project_prompt(project_id)


def load_project_prompt(project_id: str | None) -> tuple[str, dict[str, Any]]:
    if not project_id:
        return "", {"project_id": None, "status": "not_applicable", "version": 0}
    result = get_project_prompt(project_id)
    if result["status"] == "missing":
        raise FileNotFoundError(f"Project prompt is missing for project {project_id}.")
    canonical_path = _prompt_path(project_id)
    content = canonical_path.read_text(encoding="utf-8")
    metadata = {k: v for k, v in result.items() if k != "content"}
    active_version = metadata.get("active_version")
    if active_version:
        status = "active" if metadata.get("status") == "active" else "active_with_pending_changes"
        version = active_version
        notice = (
            "\\nA newer Project Prompt draft is pending review. Continue using the last approved canonical project_prompt.md."
            if metadata.get("status") == "pending_review" else ""
        )
    else:
        status = "pending_review"
        version = metadata.get("version", 0)
        notice = "\\nThis initial project prompt is pending Product Owner review; treat it as a draft baseline."
    header = (
        f"# P4 — Project Instructions\\n"
        f"Project ID: {project_id}\\n"
        f"Prompt version: {version}\\n"
        f"Prompt status: {status}{notice}\\n"
    )
    return header + "\\n" + content, {
        "project_id": project_id, "status": status, "version": version,
        "candidate_version": metadata.get("version", 0), "active_version": active_version,
    }
