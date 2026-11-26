"""Local smoke test: python -m backend.smoke_test_database
Uses a temporary database and does not touch the user's real data."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_tmp = tempfile.TemporaryDirectory(prefix="local-agent-db-test-")
os.environ["LOCAL_AGENT_DB_PATH"] = str(Path(_tmp.name) / "test.db")

from fastapi.testclient import TestClient
from backend.main import app


def main() -> None:
    with TestClient(app) as client:
        status = client.get("/api/v1/database/status")
        assert status.status_code == 200, status.text
        payload = status.json()
        assert payload["table_count"] == 19, payload
        assert "sys_project_proposals" in payload["tables"], payload
        assert payload["agents"] >= 7, payload

        project = client.post("/api/v1/projects", json={"name": "Smoke Test Project"})
        assert project.status_code == 201, project.text
        project_id = project.json()["id"]

        agents = client.get("/api/v1/agents").json()
        developer = next(agent for agent in agents if agent["role"] == "developer")
        task = client.post("/api/v1/tasks", json={
            "project_id": project_id,
            "name": "Smoke Test Task",
            "completion_criteria": "Smoke test passes",
            "estimated_duration_minutes": 30,
        })
        assert task.status_code == 201, task.text
        task_id = task.json()["id"]

        assignment = client.post(f"/api/v1/tasks/{task_id}/assign", json={"agent_id": developer["id"]})
        assert assignment.status_code == 200, assignment.text
        started = client.patch(f"/api/v1/tasks/{task_id}", json={"status": "in_progress"})
        assert started.status_code == 200, started.text
        completed = client.patch(f"/api/v1/tasks/{task_id}", json={"status": "completed"})
        assert completed.status_code == 200, completed.text

        existing_project_count = len(client.get("/api/v1/projects").json())
        proposal = client.post("/api/v1/proposals", json={
            "title": "Proposal Approval Smoke Test",
            "objective": "Verify the approval gate.",
            "scope": {"in_scope": ["proposal workflow"], "out_of_scope": []},
            "deliverables": ["Approved project"],
            "milestones": [{"name": "Approval"}],
            "tasks": [{"id": "task-1", "name": "Create approved task", "completion_criteria": "Task exists"}],
            "timeline": {"duration": "1 day"},
            "risks": [],
        })
        assert proposal.status_code == 201, proposal.text
        proposal_id = proposal.json()["id"]
        assert proposal.json()["status"] == "pending_approval"
        assert len(client.get("/api/v1/projects").json()) == existing_project_count
        approved = client.post(f"/api/v1/proposals/{proposal_id}/decision", json={"action": "approve"})
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        assert len(client.get("/api/v1/projects").json()) == existing_project_count + 1
        assert len(client.get(f"/api/v1/projects/{approved.json()['project']['id']}/tasks").json()) == 1

        rejected = client.post("/api/v1/proposals", json={
            "title": "Rejected Proposal", "objective": "Must not create a project.",
            "scope": {}, "deliverables": [], "milestones": [], "tasks": [], "timeline": {}, "risks": [],
        })
        rejected_id = rejected.json()["id"]
        rejected_result = client.post(f"/api/v1/proposals/{rejected_id}/decision", json={"action": "reject"})
        assert rejected_result.status_code == 200 and rejected_result.json()["status"] == "rejected"
        assert len(client.get("/api/v1/projects").json()) == existing_project_count + 1

        print("PASS: SQLite schema, default Agents, project/task creation, assignment and status transitions")
        print("PASS: Proposal submission, approval gate, approved Project/Task creation, and rejection without Project creation")
        print(f"PASS: {payload['table_count']} tables initialized in a temporary database")


if __name__ == "__main__":
    main()
