from __future__ import annotations

VERSION = 2
NAME = "project_lifecycle_governance"


def load_sql() -> str:
    return """
    CREATE TABLE IF NOT EXISTS sys_project_lifecycle (
        id TEXT PRIMARY KEY,
        proposal_id TEXT UNIQUE REFERENCES sys_project_proposals(id) ON DELETE CASCADE,
        project_id TEXT UNIQUE REFERENCES sys_projects(id) ON DELETE SET NULL,
        lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN (
            'proposal_submitted', 'approved_in_principle', 'planning_authorized',
            'formal_project_approved', 'execution_authorized', 'in_progress',
            'pending_acceptance', 'accepted', 'rejected'
        )),
        transition_comment TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_sys_project_lifecycle_status
        ON sys_project_lifecycle(lifecycle_status, updated_at);

    INSERT INTO sys_project_lifecycle(
        id, proposal_id, project_id, lifecycle_status, transition_comment, created_at, updated_at
    )
    SELECT
        lower(hex(randomblob(16))), p.id, p.project_id,
        CASE
            WHEN p.project_id IS NOT NULL THEN 'formal_project_approved'
            WHEN p.status = 'approved' THEN 'approved_in_principle'
            WHEN p.status = 'rejected' THEN 'rejected'
            ELSE 'proposal_submitted'
        END,
        'Lifecycle state backfilled during V2.2 migration.', p.created_at, p.updated_at
    FROM sys_project_proposals p
    WHERE NOT EXISTS (
        SELECT 1 FROM sys_project_lifecycle l WHERE l.proposal_id = p.id
    );

    INSERT INTO sys_project_lifecycle(
        id, proposal_id, project_id, lifecycle_status, transition_comment, created_at, updated_at
    )
    SELECT
        lower(hex(randomblob(16))), NULL, p.id, 'formal_project_approved',
        'Existing standalone project backfilled during V2.2 migration.', p.created_at, p.updated_at
    FROM sys_projects p
    WHERE NOT EXISTS (
        SELECT 1 FROM sys_project_lifecycle l WHERE l.project_id = p.id
    );
    """
