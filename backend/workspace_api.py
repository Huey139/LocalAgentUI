from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .database import PROJECT_ROOT, connect, now_iso, new_id

router = APIRouter(prefix="/api", tags=["Context, Workspaces and Artifacts"])
WORKSPACE_ROOT = (PROJECT_ROOT / "workspaces").resolve()
GLOBAL_ROOT = (PROJECT_ROOT / "global").resolve()


def _safe_child(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise HTTPException(400, "The requested path is outside the permitted workspace.")
    return resolved


def _workspace_root(workspace_type: str, workspace_id: str) -> Path:
    if workspace_type == "temporary":
        return _safe_child(WORKSPACE_ROOT, WORKSPACE_ROOT / "temporary" / workspace_id)
    if workspace_type == "project":
        return _safe_child(WORKSPACE_ROOT, WORKSPACE_ROOT / "projects" / workspace_id)
    return _safe_child(GLOBAL_ROOT, GLOBAL_ROOT / "outputs" / workspace_id)


class ContextUpdate(BaseModel):
    object_type: str | None = None
    object_id: str | None = None
    project_id: str | None = None
    proposal_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class WorkspaceCreate(BaseModel):
    workspace_type: str = "temporary"
    name: str = Field(min_length=1, max_length=160)
    chat_id: str | None = None
    project_id: str | None = None
    retention_days: int | None = Field(default=30, ge=1, le=3650)


class WorkspaceUpdate(BaseModel):
    status: str


class ArtifactStatusUpdate(BaseModel):
    status: str


class ArtifactRegister(BaseModel):
    workspace_id: str
    file_path: str
    artifact_name: str | None = None
    artifact_type: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    status: str = "validated"
    source_artifact_id: str | None = None


@router.get("/chats/{chat_id}/context")
def get_business_context(chat_id: str):
    with connect() as conn:
        row = conn.execute("SELECT * FROM sys_business_contexts WHERE chat_id=?", (chat_id,)).fetchone()
    if not row:
        return {"chat_id": chat_id, "object_type": None, "object_id": None, "project_id": None, "proposal_id": None, "context": {}}
    result = dict(row)
    for key in ("context_json", "last_result_json", "pending_decision_json"):
        raw = result.pop(key, None)
        result[key.removesuffix("_json")] = json.loads(raw) if raw else None
    return result


@router.put("/chats/{chat_id}/context")
def update_business_context(chat_id: str, payload: ContextUpdate):
    if payload.object_type and payload.object_type not in {"proposal", "project", "task", "team_plan"}:
        raise HTTPException(400, "Unsupported business object type.")
    proposal_id = payload.proposal_id or (payload.object_id if payload.object_type == "proposal" else None)
    project_id = payload.project_id or (payload.object_id if payload.object_type == "project" else None)
    if payload.object_type in {"proposal", "project"} and not payload.object_id:
        raise HTTPException(400, "object_id is required when binding a Proposal or Project.")
    with connect() as conn:
        if payload.object_type == "proposal" and payload.object_id != proposal_id:
            raise HTTPException(400, "Proposal object_id and proposal_id must match.")
        if payload.object_type == "project" and payload.object_id != project_id:
            raise HTTPException(400, "Project object_id and project_id must match.")
        if proposal_id and not conn.execute("SELECT 1 FROM sys_project_proposals WHERE id=?", (proposal_id,)).fetchone():
            raise HTTPException(404, "Proposal not found.")
        if project_id and not conn.execute("SELECT 1 FROM sys_projects WHERE id=?", (project_id,)).fetchone():
            raise HTTPException(404, "Project not found.")
        if payload.object_type == "task" and not conn.execute("SELECT 1 FROM sys_tasks WHERE id=?", (payload.object_id,)).fetchone():
            raise HTTPException(404, "Task not found.")
        if payload.object_type == "team_plan" and not conn.execute("SELECT 1 FROM sys_team_plans WHERE id=?", (payload.object_id,)).fetchone():
            raise HTTPException(404, "Team Plan not found.")
        stamp = now_iso()
        conn.execute("""INSERT INTO sys_business_contexts(chat_id,object_type,object_id,project_id,proposal_id,context_json,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET object_type=excluded.object_type,object_id=excluded.object_id,
            project_id=excluded.project_id,proposal_id=excluded.proposal_id,context_json=excluded.context_json,updated_at=excluded.updated_at""",
            (chat_id, payload.object_type, payload.object_id, project_id, proposal_id,
             json.dumps(payload.context, ensure_ascii=False), stamp, stamp))
        conn.execute("INSERT INTO sys_execution_evidence(evidence_id,chat_id,action,object_type,object_id,status,result_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (new_id(), chat_id, "business_context.bind", payload.object_type, payload.object_id, "succeeded", json.dumps({"project_id": project_id, "proposal_id": proposal_id}), stamp))
    return get_business_context(chat_id)


@router.post("/workspaces", status_code=201)
def create_workspace(payload: WorkspaceCreate):
    if payload.workspace_type not in {"temporary", "project", "global"}:
        raise HTTPException(400, "workspace_type must be temporary, project, or global.")
    if payload.workspace_type == "project":
        if not payload.project_id:
            raise HTTPException(400, "Project workspace requires project_id.")
        with connect() as conn:
            if not conn.execute("SELECT 1 FROM sys_projects WHERE id=?", (payload.project_id,)).fetchone():
                raise HTTPException(404, "Project not found.")
    elif payload.project_id:
        raise HTTPException(400, "Only project workspaces may be directly associated with project_id.")
    workspace_id = str(uuid.uuid4())
    root = _workspace_root(payload.workspace_type, payload.project_id or workspace_id)
    if payload.workspace_type == "project":
        root = _safe_child(WORKSPACE_ROOT, WORKSPACE_ROOT / "projects" / payload.project_id)
    root.mkdir(parents=True, exist_ok=True)
    for folder in ("inputs", "workspace", "outputs"):
        (root / folder).mkdir(exist_ok=True)
    if payload.workspace_type == "project":
        (root / "deliverables").mkdir(exist_ok=True)
    expires = (datetime.now(timezone.utc) + timedelta(days=payload.retention_days)).isoformat(timespec="seconds") if payload.workspace_type == "temporary" and payload.retention_days else None
    stamp = now_iso()
    with connect() as conn:
        conn.execute("INSERT INTO sys_workspaces(workspace_id,workspace_type,project_id,chat_id,name,root_path,status,expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?,'created',?,?,?)",
                     (workspace_id, payload.workspace_type, payload.project_id, payload.chat_id, payload.name.strip(), str(root), expires, stamp, stamp))
    return {"workspace_id": workspace_id, "workspace_type": payload.workspace_type, "name": payload.name.strip(), "root_path": str(root), "status": "created", "expires_at": expires}


@router.get("/workspaces")
def list_workspaces(chat_id: str | None = None, project_id: str | None = None, limit: int = 100):
    limit = max(1, min(limit, 500))
    clauses, params = [], []
    if chat_id:
        clauses.append("chat_id=?"); params.append(chat_id)
    if project_id:
        clauses.append("project_id=?"); params.append(project_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect() as conn:
        rows = conn.execute(f"SELECT * FROM sys_workspaces{where} ORDER BY created_at DESC LIMIT ?", (*params, limit)).fetchall()
    return [dict(row) for row in rows]


@router.patch("/workspaces/{workspace_id}")
def update_workspace(workspace_id: str, payload: WorkspaceUpdate):
    if payload.status not in {"in_progress", "completed", "archived", "expired"}:
        raise HTTPException(400, "Invalid workspace status.")
    with connect() as conn:
        cur = conn.execute("UPDATE sys_workspaces SET status=?,updated_at=? WHERE workspace_id=?", (payload.status, now_iso(), workspace_id))
        if not cur.rowcount:
            raise HTTPException(404, "Workspace not found.")
        row = conn.execute("SELECT * FROM sys_workspaces WHERE workspace_id=?", (workspace_id,)).fetchone()
    return dict(row)


@router.post("/artifacts", status_code=201)
def register_artifact(payload: ArtifactRegister):
    with connect() as conn:
        workspace = conn.execute("SELECT * FROM sys_workspaces WHERE workspace_id=?", (payload.workspace_id,)).fetchone()
        if not workspace:
            raise HTTPException(404, "Workspace not found.")
        root = Path(workspace["root_path"]).resolve()
        candidate = Path(payload.file_path)
        if not candidate.is_absolute():
            candidate = root / candidate
        path = _safe_child(root, candidate)
        if not path.is_file():
            raise HTTPException(404, "Artifact file does not exist inside the workspace.")
        if payload.status not in {"draft", "validated", "in_review", "approved", "delivered", "archived"}:
            raise HTTPException(400, "Invalid artifact status.")
        hasher = hashlib.sha256()
        with path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        stat = path.stat()
        name = Path(payload.artifact_name or path.name).name
        if not name or name in {".", ".."}:
            raise HTTPException(400, "Invalid artifact name.")
        artifact_id = new_id()
        stamp = now_iso()
        kind = payload.artifact_type or path.suffix.lstrip(".").lower() or "file"
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        previous = conn.execute("SELECT artifact_id,version FROM sys_artifacts WHERE workspace_id=? AND artifact_name=? ORDER BY version DESC LIMIT 1", (payload.workspace_id, name)).fetchone()
        version = int(previous["version"]) + 1 if previous else 1
        source_artifact_id = payload.source_artifact_id or (previous["artifact_id"] if previous else None)
        conn.execute("""INSERT INTO sys_artifacts(artifact_id,workspace_id,project_id,task_id,agent_id,artifact_name,artifact_type,mime_type,file_path,file_size,checksum,version,status,source_artifact_id,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (artifact_id, payload.workspace_id, workspace["project_id"], payload.task_id, payload.agent_id,
            name, kind, mime, str(path), stat.st_size, digest, version, payload.status, source_artifact_id, stamp))
        conn.execute("INSERT INTO sys_execution_evidence(evidence_id,workspace_id,action,object_type,object_id,status,result_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (new_id(), payload.workspace_id, "artifact.register", "artifact", artifact_id, "succeeded", json.dumps({"name": name, "size": stat.st_size, "sha256": digest}), stamp))
    return {"artifact_id": artifact_id, "workspace_id": payload.workspace_id, "artifact_name": name, "artifact_type": kind, "file_size": stat.st_size, "checksum": digest, "version": version, "status": payload.status, "download_url": f"/api/artifacts/{artifact_id}/download"}


@router.get("/artifacts")
def list_artifacts(workspace_id: str | None = None, project_id: str | None = None, limit: int = 100):
    limit = max(1, min(limit, 500))
    clauses, params = [], []
    if workspace_id:
        clauses.append("workspace_id=?"); params.append(workspace_id)
    if project_id:
        clauses.append("project_id=?"); params.append(project_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect() as conn:
        rows = conn.execute(f"SELECT artifact_id,workspace_id,project_id,task_id,agent_id,artifact_name,artifact_type,mime_type,file_size,checksum,version,status,created_at FROM sys_artifacts{where} ORDER BY created_at DESC LIMIT ?", (*params, limit)).fetchall()
    return [{**dict(r), "download_url": f"/api/artifacts/{r['artifact_id']}/download"} for r in rows]


@router.patch("/artifacts/{artifact_id}")
def update_artifact_status(artifact_id: str, payload: ArtifactStatusUpdate):
    transitions = {
        "draft": {"validated", "in_review", "archived"},
        "validated": {"in_review", "approved", "archived"},
        "in_review": {"draft", "approved", "archived"},
        "approved": {"delivered", "archived"},
        "delivered": {"archived"},
        "archived": set(),
    }
    with connect() as conn:
        row = conn.execute("SELECT status,workspace_id FROM sys_artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Artifact not found.")
        if payload.status not in transitions:
            raise HTTPException(400, "Invalid artifact status.")
        if payload.status not in transitions[row["status"]]:
            raise HTTPException(409, f"Artifact status cannot transition from {row['status']} to {payload.status}.")
        conn.execute("UPDATE sys_artifacts SET status=? WHERE artifact_id=?", (payload.status, artifact_id))
        conn.execute("INSERT INTO sys_execution_evidence(evidence_id,workspace_id,action,object_type,object_id,status,result_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (new_id(), row["workspace_id"], "artifact.status_change", "artifact", artifact_id, "succeeded", json.dumps({"from": row["status"], "to": payload.status}), now_iso()))
        result = conn.execute("SELECT artifact_id,workspace_id,artifact_name,version,status,created_at FROM sys_artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()
    return dict(result)


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str):
    with connect() as conn:
        row = conn.execute("SELECT a.*,w.root_path FROM sys_artifacts a JOIN sys_workspaces w ON w.workspace_id=a.workspace_id WHERE a.artifact_id=?", (artifact_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Artifact not found.")
    path = _safe_child(Path(row["root_path"]), Path(row["file_path"]))
    if not path.is_file():
        raise HTTPException(410, "Artifact file is no longer available.")
    return FileResponse(path, media_type=row["mime_type"] or "application/octet-stream", filename=row["artifact_name"])


def register_workspace_tools(manager: Any, *, chat_id: str, project_id: str | None = None) -> None:
    """Expose governed workspace creation and text-output registration to Main Agent."""
    def create_handler(args: dict[str, Any]) -> dict[str, Any]:
        workspace_type = "project" if project_id else str(args.get("workspace_type", "temporary"))
        payload = WorkspaceCreate(
            workspace_type=workspace_type,
            name=str(args.get("name") or "Temporary task workspace"),
            chat_id=chat_id,
            project_id=project_id if workspace_type == "project" else None,
            retention_days=int(args.get("retention_days", 30)),
        )
        result = create_workspace(payload)
        with connect() as conn:
            conn.execute("UPDATE sys_workspaces SET status='in_progress',updated_at=? WHERE workspace_id=?", (now_iso(), result["workspace_id"]))
        result["status"] = "in_progress"
        return result

    def write_handler(args: dict[str, Any]) -> dict[str, Any]:
        workspace_id = str(args.get("workspace_id", ""))
        relative = Path(str(args.get("relative_path", "")))
        if relative.is_absolute() or not relative.parts or any(part in {"..", "."} for part in relative.parts):
            raise ValueError("relative_path must be a safe path under outputs/.")
        if relative.suffix.lower() not in {".csv", ".json", ".md", ".txt", ".sql", ".py", ".yaml", ".yml"}:
            raise ValueError("This output tool supports text-based CSV, JSON, Markdown, text, SQL, Python and YAML files.")
        content = str(args.get("content", ""))
        if len(content.encode("utf-8")) > 5_000_000:
            raise ValueError("Output exceeds the 5 MB limit.")
        with connect() as conn:
            workspace = conn.execute("SELECT * FROM sys_workspaces WHERE workspace_id=?", (workspace_id,)).fetchone()
        if not workspace:
            raise ValueError("Workspace does not exist.")
        if workspace["chat_id"] != chat_id:
            raise PermissionError("Workspace does not belong to the current Chat.")
        root = Path(workspace["root_path"]).resolve()
        output_root = _safe_child(root, root / "outputs")
        target = _safe_child(output_root, output_root / relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(target)
        result = register_artifact(ArtifactRegister(workspace_id=workspace_id, file_path=str(target), status="validated"))
        with connect() as conn:
            conn.execute("UPDATE sys_workspaces SET status='completed',updated_at=? WHERE workspace_id=?", (now_iso(), workspace_id))
        return {"workspace_id": workspace_id, **result}

    manager.register(
        "create_task_workspace",
        "Create a managed workspace for a one-off task (temporary) or the current formal project. Use this before creating downloadable task output. No Proposal or Project approval is needed for a temporary workspace.",
        {"type": "object", "properties": {"name": {"type": "string"}, "workspace_type": {"type": "string", "enum": ["temporary", "project"]}, "retention_days": {"type": "integer", "minimum": 1, "maximum": 3650}}, "required": ["name"], "additionalProperties": False},
        create_handler,
    )
    manager.register(
        "write_workspace_output",
        "Write a text-based output file under the outputs/ folder of a workspace owned by this Chat, then register it in the Artifact Registry and return a verified artifact ID and download URL. Supported extensions: csv, json, md, txt, sql, py, yaml, yml.",
        {"type": "object", "properties": {"workspace_id": {"type": "string"}, "relative_path": {"type": "string"}, "content": {"type": "string"}}, "required": ["workspace_id", "relative_path", "content"], "additionalProperties": False},
        write_handler,
    )


def register_business_context_tool(manager: Any, *, chat_id: str, on_project_bound=None) -> None:
    def bind_handler(args: dict[str, Any]) -> dict[str, Any]:
        object_type = str(args.get("object_type", ""))
        object_id = str(args.get("object_id", ""))
        if object_type not in {"proposal", "project", "task", "team_plan"} or not object_id:
            raise ValueError("Provide a supported object_type and exact object_id.")
        payload = ContextUpdate(object_type=object_type, object_id=object_id,
                                proposal_id=object_id if object_type == "proposal" else None,
                                project_id=object_id if object_type == "project" else None,
                                context={"selection_source": "Main Agent tool", "selected_at": now_iso()})
        result = update_business_context(chat_id, payload)
        if object_type == "project" and on_project_bound:
            on_project_bound(object_id)
        return {"bound": True, "chat_id": chat_id, "object_type": object_type, "object_id": object_id, "context": result}

    manager.register(
        "bind_business_context",
        "Persist the exact Proposal, Project, Task or Team Plan explicitly selected by the user as the current business object for this Chat. Only call after resolving a unique exact database ID; never guess based on list order without matching the user's selection.",
        {"type": "object", "properties": {"object_type": {"type": "string", "enum": ["proposal", "project", "task", "team_plan"]}, "object_id": {"type": "string"}}, "required": ["object_type", "object_id"], "additionalProperties": False},
        bind_handler,
    )
