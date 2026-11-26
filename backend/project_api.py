from __future__ import annotations

import json
import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .database import connect, new_id, now_iso
from .project_prompts import initialise_project_prompt, get_project_prompt, update_project_prompt, activate_project_prompt
from .governance.approval_manager import ApprovalManager, ProjectLifecycle

router = APIRouter(prefix="/api/v1", tags=["Project Management"])

PROJECT_STATUSES = {"planning", "active", "on_hold", "completed", "closed", "cancelled"}
TASK_STATUSES = {"not_started", "in_progress", "blocked", "under_review", "rework_required", "completed", "cancelled"}
AGENT_STATUSES = {"available", "assigned", "working", "waiting", "reviewing", "error", "disabled"}
PRIORITIES = {"low", "medium", "high", "critical"}

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    objective: str = ""
    priority: str = "medium"
    baseline_due_date: str | None = None
    current_due_date: str | None = None

class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    objective: str | None = None
    status: str | None = None
    priority: str | None = None
    baseline_due_date: str | None = None
    current_due_date: str | None = None
    forecast_due_date: str | None = None

class TaskCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    parent_task_id: str | None = None
    priority: str = "medium"
    planned_start: str | None = None
    planned_due: str | None = None
    estimated_duration_minutes: int | None = Field(default=None, ge=0)
    completion_criteria: str = ""

class TaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    parent_task_id: str | None = None
    status: str | None = None
    priority: str | None = None
    planned_start: str | None = None
    planned_due: str | None = None
    forecast_due: str | None = None
    estimated_duration_minutes: int | None = Field(default=None, ge=0)
    completion_criteria: str | None = None
    output_summary: str | None = None

class AgentUpdate(BaseModel):
    status: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    permissions: list[str] | None = None

class AssignmentCreate(BaseModel):
    agent_id: str
    assignment_type: str = "primary"

class DependencyCreate(BaseModel):
    depends_on_task_id: str

class ProjectPromptUpdate(BaseModel):
    content: str = Field(min_length=1)
    change_summary: str = "Project prompt updated by Product Owner."


def _dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def _log(conn: sqlite3.Connection, action: str, project_id: str | None = None, task_id: str | None = None, agent_id: str | None = None, details: dict[str, Any] | None = None) -> None:
    conn.execute(
        "INSERT INTO sys_activity_logs(id,project_id,task_id,agent_id,actor_type,action,details_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (new_id(), project_id, task_id, agent_id, "user", action, json.dumps(details or {}, ensure_ascii=False), now_iso()),
    )


def _check_priority(value: str) -> None:
    if value not in PRIORITIES:
        raise HTTPException(400, "priority 必须是 low、medium、high 或 critical")



@router.post("/projects/{project_id}/prompt/initialize")
def create_project_prompt_baseline(project_id: str):
    with connect() as conn:
        row = conn.execute("SELECT * FROM sys_projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            raise HTTPException(404, "项目不存在")
    return initialise_project_prompt(project_id, dict(row), {})


@router.get("/projects/{project_id}/prompt")
def read_project_prompt(project_id: str):
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM sys_projects WHERE id=?", (project_id,)).fetchone():
            raise HTTPException(404, "项目不存在")
    result = get_project_prompt(project_id)
    if result.get("status") == "missing":
        raise HTTPException(404, "项目 Prompt 尚未初始化")
    return result


@router.patch("/projects/{project_id}/prompt")
def edit_project_prompt(project_id: str, payload: ProjectPromptUpdate):
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM sys_projects WHERE id=?", (project_id,)).fetchone():
            raise HTTPException(404, "项目不存在")
    try:
        return update_project_prompt(project_id, payload.content, payload.change_summary)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/projects/{project_id}/prompt/activate")
def approve_project_prompt(project_id: str):
    """Product Owner activates the reviewed project prompt baseline."""
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM sys_projects WHERE id=?", (project_id,)).fetchone():
            raise HTTPException(404, "项目不存在")
    try:
        return activate_project_prompt(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


def is_project_execution_authorized(project_id: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT lifecycle_status FROM sys_project_lifecycle WHERE project_id=?",
            (project_id,),
        ).fetchone()
    if not row or row["lifecycle_status"] not in {
        ProjectLifecycle.EXECUTION_AUTHORIZED.value,
        ProjectLifecycle.IN_PROGRESS.value,
    }:
        return False
    try:
        prompt = get_project_prompt(project_id)
    except (OSError, ValueError):
        return False
    return bool(prompt.get("active_version"))


@router.get("/database/status")
def database_status():
    with connect() as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        agent_count = conn.execute("SELECT COUNT(*) FROM sys_agents").fetchone()[0]
        project_count = conn.execute("SELECT COUNT(*) FROM sys_projects").fetchone()[0]
        task_count = conn.execute("SELECT COUNT(*) FROM sys_tasks").fetchone()[0]
        schema_version = conn.execute("SELECT COALESCE(MAX(version),0) FROM sys_schema_migrations").fetchone()[0]
    return {"database": "sqlite", "status": "ready", "schema_version": schema_version, "tables": tables, "table_count": len(tables), "agents": agent_count, "projects": project_count, "tasks": task_count}

@router.post("/projects/{project_id}/authorize-execution")
def authorize_project_execution(project_id: str):
    """Product Owner explicitly authorises execution after formal project approval."""
    with connect() as conn:
        lifecycle = conn.execute("SELECT * FROM sys_project_lifecycle WHERE project_id=?", (project_id,)).fetchone()
        if not lifecycle:
            raise HTTPException(404, "项目生命周期记录不存在")
        try:
            ApprovalManager.validate_transition(lifecycle["lifecycle_status"], ProjectLifecycle.EXECUTION_AUTHORIZED)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        stamp = now_iso()
        conn.execute("UPDATE sys_project_lifecycle SET lifecycle_status=?,transition_comment=?,updated_at=? WHERE project_id=?", (ProjectLifecycle.EXECUTION_AUTHORIZED.value, "Execution explicitly authorised by Product Owner.", stamp, project_id))
        _log(conn, "project.execution_authorized", project_id, details={"lifecycle_status": ProjectLifecycle.EXECUTION_AUTHORIZED.value})
        return {"project_id": project_id, "lifecycle_status": ProjectLifecycle.EXECUTION_AUTHORIZED.value, "execution_authorized": True}


@router.post("/projects/{project_id}/submit-for-acceptance")
def submit_project_for_acceptance(project_id: str):
    with connect() as conn:
        lifecycle = conn.execute("SELECT * FROM sys_project_lifecycle WHERE project_id=?", (project_id,)).fetchone()
        if not lifecycle:
            raise HTTPException(404, "项目生命周期记录不存在")
        incomplete = conn.execute("SELECT COUNT(*) FROM sys_tasks WHERE project_id=? AND status NOT IN ('completed','cancelled')", (project_id,)).fetchone()[0]
        pending_deliverables = conn.execute("SELECT COUNT(*) FROM sys_deliverables WHERE project_id=? AND status!='accepted'", (project_id,)).fetchone()[0]
        if incomplete:
            raise HTTPException(409, "仍有未完成任务，不能提交最终验收")
        if pending_deliverables:
            raise HTTPException(409, "仍有未验收的交付物，不能提交最终验收")
        try:
            ApprovalManager.validate_transition(lifecycle["lifecycle_status"], ProjectLifecycle.PENDING_ACCEPTANCE)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        stamp = now_iso()
        conn.execute("UPDATE sys_project_lifecycle SET lifecycle_status=?,updated_at=? WHERE project_id=?", (ProjectLifecycle.PENDING_ACCEPTANCE.value, stamp, project_id))
        conn.execute("UPDATE sys_projects SET status='completed',completed_at=?,updated_at=? WHERE id=?", (stamp, stamp, project_id))
        _log(conn, "project.pending_acceptance", project_id)
        return {"project_id": project_id, "lifecycle_status": ProjectLifecycle.PENDING_ACCEPTANCE.value, "accepted": False}


@router.post("/projects/{project_id}/accept")
def accept_project(project_id: str):
    """Final project acceptance is reserved for the Product Owner."""
    with connect() as conn:
        lifecycle = conn.execute("SELECT * FROM sys_project_lifecycle WHERE project_id=?", (project_id,)).fetchone()
        if not lifecycle:
            raise HTTPException(404, "项目生命周期记录不存在")
        try:
            ApprovalManager.validate_transition(lifecycle["lifecycle_status"], ProjectLifecycle.ACCEPTED)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        stamp = now_iso()
        conn.execute("UPDATE sys_project_lifecycle SET lifecycle_status=?,transition_comment='Final acceptance confirmed by Product Owner.',updated_at=? WHERE project_id=?", (ProjectLifecycle.ACCEPTED.value, stamp, project_id))
        conn.execute("UPDATE sys_projects SET status='closed',closed_at=?,updated_at=? WHERE id=?", (stamp, stamp, project_id))
        _log(conn, "project.accepted", project_id)
        return {"project_id": project_id, "lifecycle_status": ProjectLifecycle.ACCEPTED.value, "accepted": True}


@router.get("/projects")
def list_projects(status: str | None = None):
    with connect() as conn:
        if status:
            if status not in PROJECT_STATUSES: raise HTTPException(400, "无效的项目状态")
            rows = conn.execute("SELECT * FROM sys_projects WHERE status=? ORDER BY updated_at DESC", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM sys_projects ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]

@router.post("/projects", status_code=201)
def create_project(payload: ProjectCreate):
    _check_priority(payload.priority)
    project_id, stamp = new_id(), now_iso()
    with connect() as conn:
        conn.execute("INSERT INTO sys_projects(id,name,description,objective,priority,baseline_due_date,current_due_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (project_id,payload.name.strip(),payload.description,payload.objective,payload.priority,payload.baseline_due_date,payload.current_due_date or payload.baseline_due_date,stamp,stamp))
        # Direct project creation is treated as explicit formal creation by the user,
        # but it does not grant execution permission.
        conn.execute("INSERT INTO sys_project_lifecycle(id,proposal_id,project_id,lifecycle_status,transition_comment,created_at,updated_at) VALUES(?,NULL,?,'formal_project_approved','Project created directly by Product Owner.',?,?)", (new_id(), project_id, stamp, stamp))
        _log(conn, "project.created", project_id, details={"name": payload.name, "lifecycle_status": "formal_project_approved"})
        row = conn.execute("SELECT * FROM sys_projects WHERE id=?", (project_id,)).fetchone()
        project_result = dict(row)
    initialise_project_prompt(project_id, project_result, {})
    return project_result

@router.get("/projects/{project_id}")
def get_project(project_id: str):
    with connect() as conn:
        row = conn.execute("SELECT * FROM sys_projects WHERE id=?", (project_id,)).fetchone()
        if not row: raise HTTPException(404, "项目不存在")
        task_count = conn.execute("SELECT COUNT(*) FROM sys_tasks WHERE project_id=?", (project_id,)).fetchone()[0]
        completed_count = conn.execute("SELECT COUNT(*) FROM sys_tasks WHERE project_id=? AND status='completed'", (project_id,)).fetchone()[0]
        lifecycle = conn.execute("SELECT lifecycle_status FROM sys_project_lifecycle WHERE project_id=?", (project_id,)).fetchone()
    result = dict(row)
    result.update({"task_count": task_count, "completed_task_count": completed_count, "task_progress": round(completed_count / task_count * 100, 1) if task_count else 0, "lifecycle_status": lifecycle["lifecycle_status"] if lifecycle else None})
    return result

@router.patch("/projects/{project_id}")
def update_project(project_id: str, payload: ProjectUpdate):
    values = payload.model_dump(exclude_unset=True)
    if "status" in values and values["status"] not in PROJECT_STATUSES: raise HTTPException(400, "无效的项目状态")
    if "priority" in values: _check_priority(values["priority"])
    if values.get("status") == "active":
        with connect() as conn:
            lifecycle = conn.execute("SELECT lifecycle_status FROM sys_project_lifecycle WHERE project_id=?", (project_id,)).fetchone()
            if not lifecycle or lifecycle["lifecycle_status"] not in {ProjectLifecycle.EXECUTION_AUTHORIZED.value, ProjectLifecycle.IN_PROGRESS.value}:
                raise HTTPException(403, "项目尚未获得明确的执行授权，不能设为 active")
    if not values: raise HTTPException(400, "没有提供需要更新的字段")
    values["updated_at"] = now_iso()
    if values.get("status") == "completed":
        raise HTTPException(409, "请使用 submit-for-acceptance 接口提交项目验收")
    if values.get("status") == "closed":
        raise HTTPException(409, "最终验收必须通过 accept 接口完成")
    assignments = ",".join(f"{key}=?" for key in values)
    with connect() as conn:
        cur = conn.execute(f"UPDATE sys_projects SET {assignments} WHERE id=?", (*values.values(), project_id))
        if not cur.rowcount: raise HTTPException(404, "项目不存在")
        _log(conn, "project.updated", project_id, details=values)
        row = conn.execute("SELECT * FROM sys_projects WHERE id=?", (project_id,)).fetchone()
        project_result = dict(row)
    return project_result

@router.get("/projects/{project_id}/tasks")
def list_project_tasks(project_id: str):
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM sys_projects WHERE id=?", (project_id,)).fetchone(): raise HTTPException(404, "项目不存在")
        rows = conn.execute("""SELECT t.*, (SELECT a.name FROM sys_task_assignments x JOIN sys_agents a ON a.id=x.agent_id WHERE x.task_id=t.id AND x.assignment_type='primary' AND x.unassigned_at IS NULL LIMIT 1) AS assigned_agent FROM sys_tasks t WHERE t.project_id=? ORDER BY t.created_at""", (project_id,)).fetchall()
    return [dict(r) for r in rows]

@router.post("/tasks", status_code=201)
def create_task(payload: TaskCreate):
    _check_priority(payload.priority)
    task_id, stamp = new_id(), now_iso()
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM sys_projects WHERE id=?", (payload.project_id,)).fetchone(): raise HTTPException(404, "所属项目不存在")
        if payload.parent_task_id and not conn.execute("SELECT 1 FROM sys_tasks WHERE id=? AND project_id=?", (payload.parent_task_id,payload.project_id)).fetchone(): raise HTTPException(400, "父任务必须属于同一个项目")
        conn.execute("INSERT INTO sys_tasks(id,project_id,parent_task_id,name,description,priority,planned_start,planned_due,estimated_duration_minutes,completion_criteria,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (task_id,payload.project_id,payload.parent_task_id,payload.name.strip(),payload.description,payload.priority,payload.planned_start,payload.planned_due,payload.estimated_duration_minutes,payload.completion_criteria,stamp,stamp))
        _log(conn, "task.created", payload.project_id, task_id, details={"name": payload.name})
        row = conn.execute("SELECT * FROM sys_tasks WHERE id=?", (task_id,)).fetchone()
    return dict(row)

@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    with connect() as conn:
        row = conn.execute("SELECT * FROM sys_tasks WHERE id=?", (task_id,)).fetchone()
        if not row: raise HTTPException(404, "任务不存在")
        result = dict(row)
        result["assignments"] = [dict(x) for x in conn.execute("SELECT ta.*,a.name AS agent_name,a.role AS agent_role FROM sys_task_assignments ta JOIN sys_agents a ON a.id=ta.agent_id WHERE ta.task_id=? AND ta.unassigned_at IS NULL", (task_id,)).fetchall()]
        result["dependencies"] = [dict(x) for x in conn.execute("SELECT d.*,t.name AS depends_on_name FROM sys_task_dependencies d JOIN sys_tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=?", (task_id,)).fetchall()]
    return result

@router.patch("/tasks/{task_id}")
def update_task(task_id: str, payload: TaskUpdate):
    values = payload.model_dump(exclude_unset=True)
    if "status" in values and values["status"] not in TASK_STATUSES: raise HTTPException(400, "无效的任务状态")
    if "priority" in values: _check_priority(values["priority"])
    if not values: raise HTTPException(400, "没有提供需要更新的字段")
    with connect() as conn:
        current = conn.execute("SELECT * FROM sys_tasks WHERE id=?", (task_id,)).fetchone()
        if not current: raise HTTPException(404, "任务不存在")
        if values.get("parent_task_id"):
            if values["parent_task_id"] == task_id: raise HTTPException(400, "任务不能成为自己的父任务")
            if not conn.execute("SELECT 1 FROM sys_tasks WHERE id=? AND project_id=?", (values["parent_task_id"],current["project_id"])).fetchone(): raise HTTPException(400, "父任务必须属于同一个项目")
        if values.get("status") == "in_progress":
            lifecycle = conn.execute("SELECT lifecycle_status FROM sys_project_lifecycle WHERE project_id=?", (current["project_id"],)).fetchone()
            if not lifecycle or lifecycle["lifecycle_status"] not in {ProjectLifecycle.EXECUTION_AUTHORIZED.value, ProjectLifecycle.IN_PROGRESS.value}:
                raise HTTPException(403, "项目尚未获得明确的执行授权，不能启动任务")
            if lifecycle["lifecycle_status"] == ProjectLifecycle.EXECUTION_AUTHORIZED.value:
                conn.execute("UPDATE sys_project_lifecycle SET lifecycle_status=?,updated_at=? WHERE project_id=?", (ProjectLifecycle.IN_PROGRESS.value, now_iso(), current["project_id"]))
            incomplete = conn.execute("SELECT COUNT(*) FROM sys_task_dependencies d JOIN sys_tasks dep ON dep.id=d.depends_on_task_id WHERE d.task_id=? AND dep.status!='completed'", (task_id,)).fetchone()[0]
            if incomplete: raise HTTPException(409, "存在尚未完成的前置任务")
            if not current["actual_start"]: values["actual_start"] = now_iso()
        if values.get("status") == "completed":
            if not current["completion_criteria"] and not values.get("completion_criteria"):
                raise HTTPException(409, "完成任务前必须设置 completion_criteria")
            values["actual_completion"] = now_iso()
        values["updated_at"] = now_iso()
        assignments = ",".join(f"{key}=?" for key in values)
        conn.execute(f"UPDATE sys_tasks SET {assignments} WHERE id=?", (*values.values(), task_id))
        _log(conn, "task.updated", current["project_id"], task_id, details=values)
        row = conn.execute("SELECT * FROM sys_tasks WHERE id=?", (task_id,)).fetchone()
    return dict(row)

@router.post("/tasks/{task_id}/assign")
def assign_task(task_id: str, payload: AssignmentCreate):
    if payload.assignment_type not in {"primary", "support"}: raise HTTPException(400, "assignment_type 必须是 primary 或 support")
    with connect() as conn:
        task = conn.execute("SELECT project_id FROM sys_tasks WHERE id=?", (task_id,)).fetchone()
        if not task: raise HTTPException(404, "任务不存在")
        agent = conn.execute("SELECT * FROM sys_agents WHERE id=?", (payload.agent_id,)).fetchone()
        if not agent: raise HTTPException(404, "Agent 不存在")
        if agent["status"] == "disabled": raise HTTPException(409, "不能分配已禁用的 Agent")
        if payload.assignment_type == "primary":
            conn.execute("UPDATE sys_task_assignments SET unassigned_at=? WHERE task_id=? AND assignment_type='primary' AND unassigned_at IS NULL", (now_iso(),task_id))
        conn.execute("INSERT INTO sys_task_assignments(id,task_id,agent_id,assignment_type,assigned_at) VALUES(?,?,?,?,?)", (new_id(),task_id,payload.agent_id,payload.assignment_type,now_iso()))
        conn.execute("UPDATE sys_agents SET status='assigned',updated_at=? WHERE id=? AND status='available'", (now_iso(),payload.agent_id))
        _log(conn, "task.assigned", task["project_id"], task_id, payload.agent_id, {"assignment_type":payload.assignment_type})
        rows = conn.execute("SELECT ta.*,a.name AS agent_name,a.role AS agent_role FROM sys_task_assignments ta JOIN sys_agents a ON a.id=ta.agent_id WHERE ta.task_id=? AND ta.unassigned_at IS NULL", (task_id,)).fetchall()
    return [dict(r) for r in rows]

@router.post("/tasks/{task_id}/dependencies", status_code=201)
def add_task_dependency(task_id: str, payload: DependencyCreate):
    with connect() as conn:
        task = conn.execute("SELECT project_id FROM sys_tasks WHERE id=?", (task_id,)).fetchone()
        dependency = conn.execute("SELECT project_id FROM sys_tasks WHERE id=?", (payload.depends_on_task_id,)).fetchone()
        if not task or not dependency: raise HTTPException(404, "任务不存在")
        if task["project_id"] != dependency["project_id"]: raise HTTPException(400, "依赖任务必须属于同一个项目")
        if task_id == payload.depends_on_task_id: raise HTTPException(400, "任务不能依赖自身")
        # If dependency already transitively depends on task, adding this edge creates a cycle.
        cycle = conn.execute("""WITH RECURSIVE reach(id) AS (SELECT depends_on_task_id FROM sys_task_dependencies WHERE task_id=? UNION SELECT d.depends_on_task_id FROM sys_task_dependencies d JOIN reach r ON d.task_id=r.id) SELECT 1 FROM reach WHERE id=? LIMIT 1""", (payload.depends_on_task_id,task_id)).fetchone()
        if cycle: raise HTTPException(409, "该依赖关系会形成循环")
        try:
            conn.execute("INSERT INTO sys_task_dependencies(id,task_id,depends_on_task_id,created_at) VALUES(?,?,?,?)", (new_id(),task_id,payload.depends_on_task_id,now_iso()))
        except sqlite3.IntegrityError as exc: raise HTTPException(409, "该依赖关系已经存在") from exc
        _log(conn, "task.dependency_added", task["project_id"], task_id, details={"depends_on_task_id":payload.depends_on_task_id})
    return {"success": True}

@router.get("/agents")
def list_agents(status: str | None = None):
    with connect() as conn:
        if status:
            if status not in AGENT_STATUSES: raise HTTPException(400, "无效的 Agent 状态")
            rows = conn.execute("SELECT * FROM sys_agents WHERE status=? ORDER BY is_builtin DESC,name", (status,)).fetchall()
        else: rows = conn.execute("SELECT * FROM sys_agents ORDER BY is_builtin DESC,name").fetchall()
    return [{**dict(r), "permissions": json.loads(r["permissions_json"])} for r in rows]

@router.patch("/agents/{agent_id}")
def update_agent(agent_id: str, payload: AgentUpdate):
    values = payload.model_dump(exclude_unset=True)
    if "status" in values and values["status"] not in AGENT_STATUSES: raise HTTPException(400, "无效的 Agent 状态")
    if not values: raise HTTPException(400, "没有提供需要更新的字段")
    if "permissions" in values: values["permissions_json"] = json.dumps(values.pop("permissions"), ensure_ascii=False)
    values["updated_at"] = now_iso()
    assignments = ",".join(f"{key}=?" for key in values)
    with connect() as conn:
        cur = conn.execute(f"UPDATE sys_agents SET {assignments} WHERE id=?", (*values.values(),agent_id))
        if not cur.rowcount: raise HTTPException(404, "Agent 不存在")
        _log(conn, "agent.updated", agent_id=agent_id, details=values)
        row = conn.execute("SELECT * FROM sys_agents WHERE id=?", (agent_id,)).fetchone()
    return {**dict(row), "permissions": json.loads(row["permissions_json"])}

@router.get("/activity")
def list_activity(project_id: str | None = None, limit: int = Query(default=100, ge=1, le=500)):
    with connect() as conn:
        if project_id:
            rows = conn.execute("SELECT * FROM sys_activity_logs WHERE project_id=? ORDER BY created_at DESC LIMIT ?", (project_id,limit)).fetchall()
        else: rows = conn.execute("SELECT * FROM sys_activity_logs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [{**dict(r), "details": json.loads(r["details_json"])} for r in rows]
