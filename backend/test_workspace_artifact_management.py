from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from . import database
from .db.bootstrap import initialize_database
from . import workspace_api
from .tools.tool_manager import ToolManager
from .workspace_api import (
    ArtifactRegister, ContextUpdate, WorkspaceCreate,
    create_workspace, register_artifact, update_business_context, register_workspace_tools, register_business_context_tool, update_artifact_status, ArtifactStatusUpdate,
)


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(workspace_api, "WORKSPACE_ROOT", (tmp_path / "workspaces").resolve())
    monkeypatch.setattr(workspace_api, "GLOBAL_ROOT", (tmp_path / "global").resolve())
    initialize_database()
    yield tmp_path


def test_temporary_workspace_and_artifact_registration(isolated_db):
    workspace = create_workspace(WorkspaceCreate(workspace_type="temporary", name="CSV export", retention_days=7))
    root = Path(workspace["root_path"])
    output = root / "outputs" / "export.csv"
    output.write_text("id,value\n1,10\n", encoding="utf-8")

    artifact = register_artifact(ArtifactRegister(workspace_id=workspace["workspace_id"], file_path=str(output)))
    assert artifact["artifact_name"] == "export.csv"
    assert artifact["file_size"] == output.stat().st_size
    assert len(artifact["checksum"]) == 64
    assert artifact["download_url"].endswith("/download")
    output.write_text("id,value\n1,20\n", encoding="utf-8")
    next_version = register_artifact(ArtifactRegister(workspace_id=workspace["workspace_id"], file_path=str(output)))
    assert next_version["version"] == 2
    assert update_artifact_status(artifact["artifact_id"], ArtifactStatusUpdate(status="in_review"))["status"] == "in_review"
    assert update_artifact_status(artifact["artifact_id"], ArtifactStatusUpdate(status="approved"))["status"] == "approved"
    assert update_artifact_status(artifact["artifact_id"], ArtifactStatusUpdate(status="delivered"))["status"] == "delivered"


def test_artifact_registration_rejects_path_traversal(isolated_db, tmp_path):
    workspace = create_workspace(WorkspaceCreate(workspace_type="temporary", name="Secure workspace"))
    outside = tmp_path / "outside.csv"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(HTTPException) as exc:
        register_artifact(ArtifactRegister(workspace_id=workspace["workspace_id"], file_path=str(outside)))
    assert exc.value.status_code == 400


def test_business_context_is_persisted(isolated_db):
    result = update_business_context("chat-123", ContextUpdate(
        object_type=None, object_id="task-123", proposal_id=None,
        context={"selected_by": "explicit"},
    ))
    assert result["chat_id"] == "chat-123"
    assert result["object_type"] is None
    assert result["object_id"] == "task-123"
    assert result["context"] == {"selected_by": "explicit"}


def test_main_agent_workspace_tools_create_and_register_output(isolated_db):
    manager = ToolManager()
    register_workspace_tools(manager, chat_id="chat-tool")
    created = manager.execute_result("create_task_workspace", {"name": "Data export"})
    assert created["success"] is True
    workspace_id = created["result"]["workspace_id"]
    written = manager.execute_result("write_workspace_output", {
        "workspace_id": workspace_id,
        "relative_path": "customers.csv",
        "content": "customer_id,revenue\nC1,100\n",
    })
    assert written["success"] is True
    assert written["result"]["artifact_name"] == "customers.csv"


def test_workspace_tools_reject_other_chat_workspace(isolated_db):
    manager = ToolManager()
    register_workspace_tools(manager, chat_id="chat-one")
    created = manager.execute_result("create_task_workspace", {"name": "Private export"})
    workspace_id = created["result"]["workspace_id"]
    other = ToolManager()
    register_workspace_tools(other, chat_id="chat-two")
    result = other.execute_result("write_workspace_output", {
        "workspace_id": workspace_id, "relative_path": "x.csv", "content": "a\n",
    })
    assert result["success"] is False


def test_business_context_tool_binds_existing_proposal(isolated_db):
    from .proposal_api import ProposalCreate, create_proposal
    proposal = create_proposal(ProposalCreate(title="Context test", objective="Verify durable selection"))
    manager = ToolManager()
    register_business_context_tool(manager, chat_id="chat-bind")
    result = manager.execute_result("bind_business_context", {"object_type": "proposal", "object_id": proposal["id"]})
    assert result["success"] is True
    assert result["result"]["context"]["proposal_id"] == proposal["id"]
