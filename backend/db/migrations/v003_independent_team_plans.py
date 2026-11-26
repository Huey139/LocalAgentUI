from __future__ import annotations

VERSION = 3
NAME = "independent_team_plans"


def load_sql() -> str:
    return """
    CREATE TABLE IF NOT EXISTS sys_team_plans (
        id TEXT PRIMARY KEY,
        proposal_id TEXT REFERENCES sys_project_proposals(id) ON DELETE CASCADE,
        project_id TEXT REFERENCES sys_projects(id) ON DELETE SET NULL,
        version INTEGER NOT NULL CHECK (version > 0),
        status TEXT NOT NULL CHECK (status IN ('draft','proposed','owner_approved','stale','superseded')),
        plan_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        approved_at TEXT,
        CHECK (proposal_id IS NOT NULL OR project_id IS NOT NULL),
        UNIQUE(proposal_id, version),
        UNIQUE(project_id, version)
    );
    CREATE INDEX IF NOT EXISTS idx_sys_team_plans_proposal ON sys_team_plans(proposal_id, version DESC);
    CREATE INDEX IF NOT EXISTS idx_sys_team_plans_project ON sys_team_plans(project_id, version DESC);
    CREATE INDEX IF NOT EXISTS idx_sys_team_plans_status ON sys_team_plans(status, updated_at);
    """
