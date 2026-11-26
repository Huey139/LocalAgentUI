from __future__ import annotations

import json
import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .database import connect, new_id, now_iso
from .project_prompts import initialise_project_prompt
from .team_orchestration_api import PLANS, _read as _read_team_state, _write as _write_team_state
from .governance.approval_manager import ApprovalManager, ProjectLifecycle

router = APIRouter(prefix="/api/v1", tags=["Project Proposals"])
PROPOSAL_STATUSES = {"discussion", "proposal_draft", "pending_approval", "changes_requested", "approved", "rejected"}


class ProposalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1)
    scope: dict[str, Any] = Field(default_factory=dict)
    deliverables: list[Any] = Field(default_factory=list)
    milestones: list[Any] = Field(default_factory=list)
    tasks: list[Any] = Field(default_factory=list)
    agent_allocations: list[Any] = Field(default_factory=list)
    timeline: dict[str, Any] = Field(default_factory=dict)
    risks: list[Any] = Field(default_factory=list)
    assumptions: list[Any] = Field(default_factory=list)
    priority: str = "medium"
    baseline_due_date: str | None = None


class ProposalDecision(BaseModel):
    action: str = Field(pattern="^(approve|request_changes|reject)$")
    comment: str = ""


class ProposalUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    objective: str | None = None
    scope: dict[str, Any] | None = None
    deliverables: list[Any] | None = None
    milestones: list[Any] | None = None
    tasks: list[Any] | None = None
    agent_allocations: list[Any] | None = None
    timeline: dict[str, Any] | None = None
    risks: list[Any] | None = None
    assumptions: list[Any] | None = None
    priority: str | None = None
    baseline_due_date: str | None = None


class LifecycleComment(BaseModel):
    comment: str = ""


def _decode(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    for key in ("scope_json", "deliverables_json", "milestones_json", "tasks_json", "agent_allocations_json", "timeline_json", "risks_json", "assumptions_json", "approved_baseline_json"):
        raw = item.pop(key, None)
        item[key.removesuffix("_json")] = json.loads(raw) if raw else (None if key == "approved_baseline_json" else ({} if key.endswith("scope_json") or key.endswith("timeline_json") else []))
    return item


def _lifecycle(conn: sqlite3.Connection, proposal_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM sys_project_lifecycle WHERE proposal_id=?", (proposal_id,)).fetchone()
    return dict(row) if row else None


def _set_lifecycle(conn: sqlite3.Connection, proposal_id: str, target: ProjectLifecycle, comment: str = "", project_id: str | None = None) -> None:
    current = _lifecycle(conn, proposal_id)
    stamp = now_iso()
    if current:
        ApprovalManager.validate_transition(current["lifecycle_status"], target)
        conn.execute(
            "UPDATE sys_project_lifecycle SET lifecycle_status=?, transition_comment=?, project_id=COALESCE(?,project_id), updated_at=? WHERE proposal_id=?",
            (target.value, comment, project_id, stamp, proposal_id),
        )
    else:
        if target != ProjectLifecycle.PROPOSAL_SUBMITTED:
            raise HTTPException(409, "Proposal lifecycle record is missing; cannot advance governance state.")
        conn.execute(
            "INSERT INTO sys_project_lifecycle(id,proposal_id,project_id,lifecycle_status,transition_comment,created_at,updated_at) VALUES(?,?,NULL,?,?,?,?)",
            (new_id(), proposal_id, target.value, comment, stamp, stamp),
        )


def create_proposal(payload: ProposalCreate) -> dict[str, Any]:
    if payload.priority not in {"low", "medium", "high", "critical"}:
        raise HTTPException(400, "Priority must be low, medium, high, or critical.")
    proposal_id, stamp = new_id(), now_iso()
    with connect() as conn:
        conn.execute(
            """INSERT INTO sys_project_proposals
            (id,title,objective,scope_json,deliverables_json,milestones_json,tasks_json,agent_allocations_json,timeline_json,risks_json,assumptions_json,priority,baseline_due_date,status,approval_request_id,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'discussion',NULL,?,?)""",
            (proposal_id, payload.title.strip(), payload.objective, json.dumps(payload.scope, ensure_ascii=False),
             json.dumps(payload.deliverables, ensure_ascii=False), json.dumps(payload.milestones, ensure_ascii=False),
             json.dumps(payload.tasks, ensure_ascii=False), json.dumps(payload.agent_allocations, ensure_ascii=False),
             json.dumps(payload.timeline, ensure_ascii=False), json.dumps(payload.risks, ensure_ascii=False),
             json.dumps(payload.assumptions, ensure_ascii=False), payload.priority, payload.baseline_due_date, stamp, stamp),
        )
        _set_lifecycle(conn, proposal_id, ProjectLifecycle.PROPOSAL_SUBMITTED, "Proposal created for discussion; no approval requested yet.")
        conn.execute("INSERT INTO sys_activity_logs(id,actor_type,action,details_json,created_at) VALUES(?,?,?,?,?)",
                     (new_id(), "main_agent", "proposal.created_for_discussion", json.dumps({"proposal_id": proposal_id, "title": payload.title}, ensure_ascii=False), stamp))
        row = conn.execute("SELECT * FROM sys_project_proposals WHERE id=?", (proposal_id,)).fetchone()
        result = _decode(row)
        result["lifecycle"] = _lifecycle(conn, proposal_id)
    return result


@router.post("/proposals", status_code=201)
def submit_proposal(payload: ProposalCreate):
    return create_proposal(payload)


@router.patch("/proposals/{proposal_id}")
def update_proposal(proposal_id: str, payload: ProposalUpdate):
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(400, "No proposal fields were provided for update.")
    if "priority" in values and values["priority"] not in {"low", "medium", "high", "critical"}:
        raise HTTPException(400, "Priority must be low, medium, high, or critical.")
    json_fields = {"scope", "deliverables", "milestones", "tasks", "agent_allocations", "timeline", "risks", "assumptions"}
    for key in list(values):
        if key in json_fields:
            values[f"{key}_json"] = json.dumps(values.pop(key), ensure_ascii=False)
    values["status"] = "discussion"
    values["updated_at"] = now_iso()
    with connect() as conn:
        current = conn.execute("SELECT status FROM sys_project_proposals WHERE id=?", (proposal_id,)).fetchone()
        lifecycle = _lifecycle(conn, proposal_id)
        if not current:
            raise HTTPException(404, "Proposal not found.")
        if current["status"] in {"approved", "rejected"} or (lifecycle and lifecycle["lifecycle_status"] not in {"proposal_submitted", "planning_authorized"}):
            raise HTTPException(409, "This proposal can no longer be edited after formal approval or rejection.")
        allocations_row = conn.execute("SELECT agent_allocations_json FROM sys_project_proposals WHERE id=?", (proposal_id,)).fetchone()
        allocations = json.loads(allocations_row["agent_allocations_json"] or "{}") if allocations_row else {}
        if isinstance(allocations, dict) and allocations.get("team_plan"):
            allocations["team_plan"]["status"] = "stale"
            values["agent_allocations_json"] = json.dumps(allocations, ensure_ascii=False)
        conn.execute("UPDATE sys_team_plans SET status='stale',updated_at=? WHERE proposal_id=? AND status!='superseded'", (now_iso(), proposal_id))
        assignments = ",".join(f"{key}=?" for key in values)
        conn.execute(f"UPDATE sys_project_proposals SET {assignments}, status='discussion' WHERE id=?", (*values.values(), proposal_id))
        row = conn.execute("SELECT * FROM sys_project_proposals WHERE id=?", (proposal_id,)).fetchone()
        result = _decode(row)
        result["lifecycle"] = _lifecycle(conn, proposal_id)
    return result


@router.post("/proposals/{proposal_id}/submit")
def resubmit_proposal(proposal_id: str):
    stamp = now_iso()
    with connect() as conn:
        row = conn.execute("SELECT status,project_id FROM sys_project_proposals WHERE id=?", (proposal_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Proposal not found.")
        if row["project_id"]:
            raise HTTPException(409, "A formally created Proposal cannot be resubmitted.")
        if row["status"] not in {"changes_requested", "proposal_draft", "discussion"}:
            raise HTTPException(409, "Only a Proposal under discussion or with requested changes can return to discussion.")
        conn.execute("UPDATE sys_project_proposals SET status='discussion',updated_at=? WHERE id=?", (stamp, proposal_id))
        result_row = conn.execute("SELECT * FROM sys_project_proposals WHERE id=?", (proposal_id,)).fetchone()
        result = _decode(result_row)
        result["lifecycle"] = _lifecycle(conn, proposal_id)
    return result


@router.get("/proposals")
def list_proposals(status: str | None = None, limit: int = Query(default=100, ge=1, le=500)):
    if status and status not in PROPOSAL_STATUSES:
        raise HTTPException(400, "Invalid proposal status.")
    with connect() as conn:
        if status:
            rows = conn.execute("SELECT * FROM sys_project_proposals WHERE status=? ORDER BY updated_at DESC LIMIT ?", (status, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM sys_project_proposals ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        results = []
        for row in rows:
            item = _decode(row)
            item["lifecycle"] = _lifecycle(conn, item["id"])
            results.append(item)
    return results


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str):
    with connect() as conn:
        row = conn.execute("SELECT * FROM sys_project_proposals WHERE id=?", (proposal_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Proposal not found.")
        result = _decode(row)
        result["lifecycle"] = _lifecycle(conn, proposal_id)
    return result


@router.post("/proposals/{proposal_id}/decision")
def decide_proposal(proposal_id: str, payload: ProposalDecision):
    stamp = now_iso()
    with connect() as conn:
        proposal = conn.execute("SELECT * FROM sys_project_proposals WHERE id=?", (proposal_id,)).fetchone()
        if not proposal:
            raise HTTPException(404, "Proposal not found.")
        lifecycle = _lifecycle(conn, proposal_id)
        if not lifecycle or lifecycle["lifecycle_status"] != ProjectLifecycle.PROPOSAL_SUBMITTED.value:
            raise HTTPException(409, "Only a submitted proposal can receive an initial Product Owner decision.")
        approval_id = proposal["approval_request_id"]
        if payload.action == "request_changes":
            conn.execute("UPDATE sys_project_proposals SET status='changes_requested', decision_comment=?, updated_at=? WHERE id=?", (payload.comment, stamp, proposal_id))
            if approval_id:
                conn.execute("UPDATE sys_approval_requests SET status='changes_requested', decision_comment=?, decided_by_type='user', decided_at=?, updated_at=? WHERE id=?", (payload.comment, stamp, stamp, approval_id))
            conn.execute("INSERT INTO sys_activity_logs(id,actor_type,action,details_json,created_at) VALUES(?,?,?,?,?)", (new_id(), "user", "proposal.changes_requested", json.dumps({"proposal_id": proposal_id, "comment": payload.comment}), stamp))
            return {"proposal_id": proposal_id, "status": "changes_requested", "lifecycle_status": "proposal_submitted", "project": None}
        if payload.action == "reject":
            conn.execute("UPDATE sys_project_proposals SET status='rejected', decision_comment=?, decided_at=?, updated_at=? WHERE id=?", (payload.comment, stamp, stamp, proposal_id))
            conn.execute("UPDATE sys_approval_requests SET status='rejected', decision_comment=?, decided_by_type='user', decided_at=?, updated_at=? WHERE id=?", (payload.comment, stamp, stamp, approval_id))
            _set_lifecycle(conn, proposal_id, ProjectLifecycle.REJECTED, payload.comment)
            conn.execute("INSERT INTO sys_activity_logs(id,actor_type,action,details_json,created_at) VALUES(?,?,?,?,?)", (new_id(), "user", "proposal.rejected", json.dumps({"proposal_id": proposal_id, "comment": payload.comment}), stamp))
            return {"proposal_id": proposal_id, "status": "rejected", "lifecycle_status": "rejected", "project": None}

        raise HTTPException(409, "Proposal approval is completed through the formal-approval endpoint. Team Plan approval is a separate decision and is not a prerequisite for Project creation.")


@router.post("/proposals/{proposal_id}/authorize-planning")
def authorize_planning(proposal_id: str, payload: LifecycleComment):
    stamp = now_iso()
    with connect() as conn:
        proposal = conn.execute("SELECT id,status FROM sys_project_proposals WHERE id=?", (proposal_id,)).fetchone()
        if not proposal:
            raise HTTPException(404, "Proposal not found.")
        try:
            _set_lifecycle(conn, proposal_id, ProjectLifecycle.PLANNING_AUTHORIZED, payload.comment)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        conn.execute("INSERT INTO sys_activity_logs(id,actor_type,action,details_json,created_at) VALUES(?,?,?,?,?)", (new_id(), "user", "proposal.planning_authorized", json.dumps({"proposal_id": proposal_id, "comment": payload.comment}), stamp))
        return {"proposal_id": proposal_id, "lifecycle_status": ProjectLifecycle.PLANNING_AUTHORIZED.value, "execution_authorized": False}


def _validate_and_create_project(conn: sqlite3.Connection, proposal: sqlite3.Row, stamp: str) -> str:
    allocations = json.loads(proposal["agent_allocations_json"] or "{}")
    if not isinstance(allocations, dict):
        allocations = {"legacy_allocations": allocations}
    # Team Planning is an independent workstream. Formal Project Approval must not
    # implicitly approve a Team Plan or require one to exist.
    # Task decomposition and task assignment intentionally belong to the next release.
    project_id = new_id()
    conn.execute(
        "INSERT INTO sys_projects(id,name,description,objective,status,priority,baseline_due_date,current_due_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (project_id, proposal["title"], "Created from formally approved project proposal.", proposal["objective"], "planning", proposal["priority"], proposal["baseline_due_date"], proposal["baseline_due_date"], stamp, stamp),
    )
    baseline = {key: json.loads(proposal[key] or ("{}" if key in {"scope_json", "timeline_json"} else "[]"))
                for key in ("scope_json", "deliverables_json", "milestones_json", "tasks_json", "timeline_json", "risks_json", "assumptions_json")}
    baseline["agent_allocations_json"] = allocations
    conn.execute("UPDATE sys_project_proposals SET project_id=?,approved_baseline_json=?,status='approved',decided_at=?,updated_at=? WHERE id=?",
                 (project_id, json.dumps(baseline, ensure_ascii=False), stamp, stamp, proposal["id"]))
    return project_id


@router.post("/proposals/{proposal_id}/formal-approval")
def formally_approve_proposal(proposal_id: str, payload: LifecycleComment):
    stamp = now_iso()
    with connect() as conn:
        # Serialise concurrent formal-approval attempts so one Proposal cannot create duplicate Projects.
        conn.execute("BEGIN IMMEDIATE")
        proposal = conn.execute("SELECT * FROM sys_project_proposals WHERE id=?", (proposal_id,)).fetchone()
        if not proposal:
            raise HTTPException(404, "Proposal not found.")
        lifecycle = _lifecycle(conn, proposal_id)
        allocations = json.loads(proposal["agent_allocations_json"] or "{}")
        approved_team_plan = None
        team_plan_row = conn.execute(
            "SELECT plan_json FROM sys_team_plans WHERE proposal_id=? ORDER BY version DESC LIMIT 1",
            (proposal_id,),
        ).fetchone()
        if team_plan_row:
            approved_team_plan = json.loads(team_plan_row["plan_json"] or "{}")
        elif isinstance(allocations, dict):
            approved_team_plan = allocations.get("team_plan")
            if isinstance(approved_team_plan, dict):
                # One-time compatibility bridge for legacy embedded Proposal Team Plans.
                conn.execute(
                    "INSERT OR IGNORE INTO sys_team_plans(id,proposal_id,project_id,version,status,plan_json,created_at,updated_at,approved_at) VALUES(?,?,NULL,?,?,?,?,?,?)",
                    (approved_team_plan.get("team_plan_id") or new_id(), proposal_id,
                     max(1, int(approved_team_plan.get("version", 1) or 1)),
                     approved_team_plan.get("status", "draft") if approved_team_plan.get("status") in {"draft","proposed","owner_approved","stale","superseded"} else "draft",
                     json.dumps(approved_team_plan, ensure_ascii=False), approved_team_plan.get("created_at") or stamp,
                     approved_team_plan.get("updated_at") or stamp, approved_team_plan.get("approved_at")),
                )
        if proposal["project_id"]:
            project_id = proposal["project_id"]
            existing = conn.execute("SELECT * FROM sys_projects WHERE id=?", (proposal["project_id"],)).fetchone()
            if existing:
                project = dict(existing)
                already_created = True
            else:
                raise HTTPException(409, "Proposal references a project that no longer exists; manual recovery is required.")
        else:
            already_created = False
        if not already_created:
            if proposal["status"] not in {"discussion", "proposal_draft"}:
                raise HTTPException(409, "Only a current Proposal discussion draft can be formally approved. Revise requested changes before continuing.")
            if not lifecycle or lifecycle["lifecycle_status"] not in {ProjectLifecycle.PROPOSAL_SUBMITTED.value, ProjectLifecycle.PLANNING_AUTHORIZED.value}:
                raise HTTPException(409, "Only a proposal still in discussion/planning can be formally approved.")
            project_id = _validate_and_create_project(conn, proposal, stamp)
            if approved_team_plan:
                conn.execute(
                    "UPDATE sys_team_plans SET project_id=?,updated_at=? WHERE proposal_id=? AND version=(SELECT MAX(version) FROM sys_team_plans WHERE proposal_id=?)",
                    (project_id, stamp, proposal_id, proposal_id),
                )
                approved_team_plan = dict(approved_team_plan)
                approved_team_plan["project_id"] = project_id
                approved_team_plan["project_name"] = proposal["title"]
            _set_lifecycle(conn, proposal_id, ProjectLifecycle.FORMAL_PROJECT_APPROVED, payload.comment, project_id)
            conn.execute("INSERT INTO sys_activity_logs(id,project_id,actor_type,action,details_json,created_at) VALUES(?,?,?,?,?,?)", (new_id(), project_id, "user", "project.formally_approved", json.dumps({"proposal_id": proposal_id, "comment": payload.comment}), stamp))
            project = dict(conn.execute("SELECT * FROM sys_projects WHERE id=?", (project_id,)).fetchone())
        baseline = {
            key: (json.loads(proposal[key]) if proposal[key] else ({} if key == "scope_json" or key == "timeline_json" else []))
            for key in ("scope_json", "deliverables_json", "milestones_json", "tasks_json", "agent_allocations_json", "timeline_json", "risks_json", "assumptions_json")
        }
    # Prompt and project-scoped team plan are materialised only after the Project row commits.
    try:
        prompt_result = initialise_project_prompt(project_id, project, baseline)
        prompt_status = prompt_result.get("status")
        prompt_version = prompt_result.get("version")
    except Exception as exc:
        # The formal Project is already committed. A secondary prompt-file
        # materialisation failure must not turn a successful approval into an
        # ambiguous failed response; report the partial initialisation clearly.
        prompt_status = "initialisation_failed"
        prompt_version = None
        prompt_error = f"{type(exc).__name__}: {exc}"
    else:
        prompt_error = None
    if approved_team_plan:
        project_plans = _read_team_state(PLANS, {})
        approved_team_plan = dict(approved_team_plan)
        approved_team_plan.update({"project_id": project_id, "project_name": project.get("name")})
        project_plans[project_id] = approved_team_plan
        _write_team_state(PLANS, project_plans)
    return {"proposal_id": proposal_id, "project": project, "project_prompt": {
        "project_id": project_id, "status": prompt_status, "version": prompt_version,
        "error": prompt_error,
    }, "lifecycle_status": ProjectLifecycle.FORMAL_PROJECT_APPROVED.value, "execution_authorized": False,
        "tasks_created": 0, "assignments_created": 0,
        "team_plan_status": (approved_team_plan or {}).get("status", "not_started"),
        "next_step": "Complete Team Planning and Task Planning independently, then request Execution Authorization."}
