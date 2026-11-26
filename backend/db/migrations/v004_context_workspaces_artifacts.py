from __future__ import annotations

VERSION = 4
NAME = "business_context_workspaces_artifacts"


def load_sql() -> str:
    return """
    CREATE TABLE IF NOT EXISTS sys_business_contexts (
        chat_id TEXT PRIMARY KEY,
        object_type TEXT,
        object_id TEXT,
        project_id TEXT REFERENCES sys_projects(id) ON DELETE SET NULL,
        proposal_id TEXT REFERENCES sys_project_proposals(id) ON DELETE SET NULL,
        last_action TEXT,
        last_result_json TEXT,
        pending_decision_json TEXT,
        context_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_sys_business_contexts_project ON sys_business_contexts(project_id);
    CREATE INDEX IF NOT EXISTS idx_sys_business_contexts_proposal ON sys_business_contexts(proposal_id);

    CREATE TABLE IF NOT EXISTS sys_workspaces (
        workspace_id TEXT PRIMARY KEY,
        workspace_type TEXT NOT NULL CHECK(workspace_type IN ('temporary','project','global')),
        project_id TEXT REFERENCES sys_projects(id) ON DELETE SET NULL,
        chat_id TEXT,
        name TEXT NOT NULL,
        root_path TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'created' CHECK(status IN ('created','in_progress','completed','archived','expired')),
        expires_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_sys_workspaces_chat ON sys_workspaces(chat_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_sys_workspaces_project ON sys_workspaces(project_id, created_at DESC);

    CREATE TABLE IF NOT EXISTS sys_artifacts (
        artifact_id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL REFERENCES sys_workspaces(workspace_id) ON DELETE RESTRICT,
        project_id TEXT REFERENCES sys_projects(id) ON DELETE SET NULL,
        task_id TEXT,
        agent_id TEXT,
        artifact_name TEXT NOT NULL,
        artifact_type TEXT NOT NULL,
        mime_type TEXT,
        file_path TEXT NOT NULL,
        file_size INTEGER NOT NULL CHECK(file_size >= 0),
        checksum TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
        status TEXT NOT NULL DEFAULT 'validated' CHECK(status IN ('draft','validated','in_review','approved','delivered','archived')),
        source_artifact_id TEXT REFERENCES sys_artifacts(artifact_id) ON DELETE SET NULL,
        validation_result_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_sys_artifacts_workspace ON sys_artifacts(workspace_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_sys_artifacts_project ON sys_artifacts(project_id, created_at DESC);

    CREATE TABLE IF NOT EXISTS sys_execution_evidence (
        evidence_id TEXT PRIMARY KEY,
        chat_id TEXT,
        workspace_id TEXT REFERENCES sys_workspaces(workspace_id) ON DELETE SET NULL,
        action TEXT NOT NULL,
        object_type TEXT,
        object_id TEXT,
        status TEXT NOT NULL CHECK(status IN ('succeeded','failed','rejected')),
        result_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_sys_execution_evidence_chat ON sys_execution_evidence(chat_id, created_at DESC);
    """
