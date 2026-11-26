-- Local Agent Project Control Tower - Schema v2.0
-- All timestamps are UTC ISO-8601 strings. IDs are application-generated UUID strings.

CREATE TABLE IF NOT EXISTS sys_schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    execution_time_ms INTEGER NOT NULL DEFAULT 0 CHECK (execution_time_ms >= 0)
);

CREATE TABLE IF NOT EXISTS sys_agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    system_prompt TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available','assigned','working','waiting','reviewing','error','disabled')),
    permissions_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(permissions_json)),
    is_builtin INTEGER NOT NULL DEFAULT 1 CHECK (is_builtin IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sys_projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    objective TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'planning' CHECK (status IN ('planning','active','on_hold','completed','closed','cancelled')),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low','medium','high','critical')),
    baseline_due_date TEXT,
    current_due_date TEXT,
    forecast_due_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS sys_approval_requests (
    id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL CHECK (subject_type IN ('project_proposal','project_change','task_change','deliverable','other')),
    subject_id TEXT NOT NULL,
    requested_by_type TEXT NOT NULL DEFAULT 'main_agent' CHECK (requested_by_type IN ('user','main_agent','specialist_agent','system')),
    requested_by_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','changes_requested','cancelled')),
    request_payload_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(request_payload_json)),
    decision_comment TEXT NOT NULL DEFAULT '',
    decided_by_type TEXT CHECK (decided_by_type IS NULL OR decided_by_type IN ('user','main_agent','specialist_agent','system')),
    decided_by_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS sys_project_proposals (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    objective TEXT NOT NULL,
    scope_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(scope_json)),
    deliverables_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(deliverables_json)),
    milestones_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(milestones_json)),
    tasks_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(tasks_json)),
    agent_allocations_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(agent_allocations_json)),
    timeline_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(timeline_json)),
    risks_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(risks_json)),
    assumptions_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(assumptions_json)),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low','medium','high','critical')),
    baseline_due_date TEXT,
    status TEXT NOT NULL DEFAULT 'pending_approval' CHECK (status IN ('discussion','proposal_draft','pending_approval','changes_requested','approved','rejected')),
    decision_comment TEXT NOT NULL DEFAULT '',
    project_id TEXT REFERENCES sys_projects(id) ON DELETE SET NULL,
    approval_request_id TEXT REFERENCES sys_approval_requests(id) ON DELETE SET NULL,
    approved_baseline_json TEXT CHECK (approved_baseline_json IS NULL OR json_valid(approved_baseline_json)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS sys_tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES sys_projects(id) ON DELETE CASCADE,
    parent_task_id TEXT REFERENCES sys_tasks(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'not_started' CHECK (status IN ('not_started','in_progress','blocked','under_review','rework_required','completed','cancelled')),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low','medium','high','critical')),
    planned_start TEXT,
    planned_due TEXT,
    actual_start TEXT,
    actual_completion TEXT,
    forecast_due TEXT,
    estimated_duration_minutes INTEGER CHECK (estimated_duration_minutes IS NULL OR estimated_duration_minutes >= 0),
    elapsed_duration_minutes INTEGER CHECK (elapsed_duration_minutes IS NULL OR elapsed_duration_minutes >= 0),
    active_duration_minutes INTEGER CHECK (active_duration_minutes IS NULL OR active_duration_minutes >= 0),
    waiting_duration_minutes INTEGER CHECK (waiting_duration_minutes IS NULL OR waiting_duration_minutes >= 0),
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count BETWEEN 0 AND 2),
    completion_criteria TEXT NOT NULL DEFAULT '',
    output_summary TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sys_task_assignments (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES sys_tasks(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL REFERENCES sys_agents(id) ON DELETE RESTRICT,
    assignment_type TEXT NOT NULL DEFAULT 'primary' CHECK (assignment_type IN ('primary','support')),
    assigned_at TEXT NOT NULL,
    unassigned_at TEXT,
    CHECK (unassigned_at IS NULL OR unassigned_at >= assigned_at)
);

CREATE TABLE IF NOT EXISTS sys_task_dependencies (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES sys_tasks(id) ON DELETE CASCADE,
    depends_on_task_id TEXT NOT NULL REFERENCES sys_tasks(id) ON DELETE CASCADE,
    dependency_type TEXT NOT NULL DEFAULT 'finish_to_start' CHECK (dependency_type IN ('finish_to_start')),
    created_at TEXT NOT NULL,
    CHECK (task_id <> depends_on_task_id),
    UNIQUE (task_id, depends_on_task_id)
);

CREATE TABLE IF NOT EXISTS sys_task_executions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES sys_tasks(id) ON DELETE CASCADE,
    agent_id TEXT REFERENCES sys_agents(id) ON DELETE SET NULL,
    attempt_number INTEGER NOT NULL CHECK (attempt_number BETWEEN 1 AND 3),
    execution_status TEXT NOT NULL DEFAULT 'running' CHECK (execution_status IN ('running','succeeded','failed','cancelled','interrupted')),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    duration_minutes INTEGER CHECK (duration_minutes IS NULL OR duration_minutes >= 0),
    error_message TEXT NOT NULL DEFAULT '',
    result_summary TEXT NOT NULL DEFAULT '',
    UNIQUE (task_id, attempt_number)
);

CREATE TABLE IF NOT EXISTS sys_progress_records (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES sys_projects(id) ON DELETE CASCADE,
    task_id TEXT REFERENCES sys_tasks(id) ON DELETE CASCADE,
    planned_progress REAL NOT NULL DEFAULT 0 CHECK (planned_progress BETWEEN 0 AND 100),
    actual_progress REAL NOT NULL DEFAULT 0 CHECK (actual_progress BETWEEN 0 AND 100),
    forecast_progress REAL NOT NULL DEFAULT 0 CHECK (forecast_progress BETWEEN 0 AND 100),
    forecast_due_date TEXT,
    recorded_at TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sys_risks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES sys_projects(id) ON DELETE CASCADE,
    task_id TEXT REFERENCES sys_tasks(id) ON DELETE SET NULL,
    record_type TEXT NOT NULL DEFAULT 'risk' CHECK (record_type IN ('risk','issue')),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    probability TEXT NOT NULL DEFAULT 'medium' CHECK (probability IN ('low','medium','high')),
    impact TEXT NOT NULL DEFAULT 'medium' CHECK (impact IN ('low','medium','high','critical')),
    status TEXT NOT NULL DEFAULT 'identified' CHECK (status IN ('identified','monitoring','open','in_progress','resolved','closed')),
    owner_agent_id TEXT REFERENCES sys_agents(id) ON DELETE SET NULL,
    mitigation TEXT NOT NULL DEFAULT '',
    target_resolution_date TEXT,
    escalated_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sys_decisions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES sys_projects(id) ON DELETE CASCADE,
    task_id TEXT REFERENCES sys_tasks(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    original_plan TEXT NOT NULL DEFAULT '',
    proposed_options_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(proposed_options_json)),
    recommendation TEXT NOT NULL DEFAULT '',
    impact_analysis TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','changes_requested','withdrawn')),
    selected_option TEXT,
    leader_comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS sys_deliverables (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES sys_projects(id) ON DELETE CASCADE,
    task_id TEXT REFERENCES sys_tasks(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    workspace_path TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','submitted','qa_in_progress','qa_passed','qa_failed','ready_for_acceptance','accepted','rejected')),
    submitted_at TEXT,
    accepted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sys_test_records (
    id TEXT PRIMARY KEY,
    deliverable_id TEXT NOT NULL REFERENCES sys_deliverables(id) ON DELETE CASCADE,
    tester_agent_id TEXT REFERENCES sys_agents(id) ON DELETE SET NULL,
    test_name TEXT NOT NULL,
    expected_result TEXT NOT NULL DEFAULT '',
    actual_result TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'blocked' CHECK (status IN ('pass','fail','blocked')),
    evidence_path TEXT,
    executed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sys_tools (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    input_schema_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(input_schema_json)),
    output_schema_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(output_schema_json)),
    permission_scope TEXT NOT NULL DEFAULT 'restricted',
    is_builtin INTEGER NOT NULL DEFAULT 1 CHECK (is_builtin IN (0,1)),
    status TEXT NOT NULL DEFAULT 'enabled' CHECK (status IN ('enabled','disabled','deprecated')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sys_tool_versions (
    id TEXT PRIMARY KEY,
    tool_id TEXT NOT NULL REFERENCES sys_tools(id) ON DELETE CASCADE,
    version TEXT NOT NULL,
    implementation_ref TEXT NOT NULL DEFAULT '',
    config_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(config_json)),
    is_active INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0,1)),
    created_at TEXT NOT NULL,
    UNIQUE (tool_id, version)
);

CREATE TABLE IF NOT EXISTS sys_agent_tools (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES sys_agents(id) ON DELETE CASCADE,
    tool_id TEXT NOT NULL REFERENCES sys_tools(id) ON DELETE CASCADE,
    permission_level TEXT NOT NULL DEFAULT 'execute' CHECK (permission_level IN ('read','execute','admin')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
    created_at TEXT NOT NULL,
    UNIQUE (agent_id, tool_id)
);

CREATE TABLE IF NOT EXISTS sys_tool_executions (
    id TEXT PRIMARY KEY,
    tool_id TEXT REFERENCES sys_tools(id) ON DELETE SET NULL,
    tool_version_id TEXT REFERENCES sys_tool_versions(id) ON DELETE SET NULL,
    agent_id TEXT REFERENCES sys_agents(id) ON DELETE SET NULL,
    task_id TEXT REFERENCES sys_tasks(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','succeeded','failed','cancelled')),
    input_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(input_json)),
    output_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(output_json)),
    error_message TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0)
);

CREATE TABLE IF NOT EXISTS sys_activity_logs (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES sys_projects(id) ON DELETE SET NULL,
    task_id TEXT REFERENCES sys_tasks(id) ON DELETE SET NULL,
    agent_id TEXT REFERENCES sys_agents(id) ON DELETE SET NULL,
    actor_type TEXT NOT NULL DEFAULT 'system' CHECK (actor_type IN ('user','main_agent','specialist_agent','system')),
    action TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(details_json)),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sys_projects_status ON sys_projects(status);
CREATE INDEX IF NOT EXISTS idx_sys_proposals_status ON sys_project_proposals(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_sys_proposals_approval ON sys_project_proposals(approval_request_id);
CREATE INDEX IF NOT EXISTS idx_sys_tasks_project_status ON sys_tasks(project_id, status);
CREATE INDEX IF NOT EXISTS idx_sys_tasks_parent ON sys_tasks(parent_task_id);
CREATE INDEX IF NOT EXISTS idx_sys_assignments_agent_history ON sys_task_assignments(agent_id, assigned_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sys_one_active_primary_agent_per_task ON sys_task_assignments(task_id) WHERE assignment_type='primary' AND unassigned_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_sys_dependencies_target ON sys_task_dependencies(depends_on_task_id);
CREATE INDEX IF NOT EXISTS idx_sys_executions_task ON sys_task_executions(task_id, attempt_number);
CREATE INDEX IF NOT EXISTS idx_sys_progress_project_date ON sys_progress_records(project_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_sys_risks_project_status ON sys_risks(project_id, status);
CREATE INDEX IF NOT EXISTS idx_sys_decisions_project_status ON sys_decisions(project_id, status);
CREATE INDEX IF NOT EXISTS idx_sys_deliverables_project_status ON sys_deliverables(project_id, status);
CREATE INDEX IF NOT EXISTS idx_sys_approvals_subject_status ON sys_approval_requests(subject_type, subject_id, status);
CREATE INDEX IF NOT EXISTS idx_sys_tools_status ON sys_tools(status, category);
CREATE INDEX IF NOT EXISTS idx_sys_tool_versions_active ON sys_tool_versions(tool_id, is_active);
CREATE INDEX IF NOT EXISTS idx_sys_tool_executions_task_date ON sys_tool_executions(task_id, started_at);
CREATE INDEX IF NOT EXISTS idx_sys_activity_project_date ON sys_activity_logs(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_sys_activity_task_date ON sys_activity_logs(task_id, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sys_one_active_tool_version
ON sys_tool_versions(tool_id) WHERE is_active = 1;
CREATE UNIQUE INDEX IF NOT EXISTS idx_sys_one_pending_approval_per_subject
ON sys_approval_requests(subject_type, subject_id) WHERE status = 'pending';

-- Preserve a lightweight audit event before parent rows are removed.
CREATE TRIGGER IF NOT EXISTS trg_sys_projects_before_delete
BEFORE DELETE ON sys_projects
BEGIN
    INSERT INTO sys_activity_logs(id, project_id, actor_type, action, details_json, created_at)
    VALUES (
        lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-a' || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))),
        OLD.id, 'system', 'project.deleted', json_object('project_id', OLD.id, 'name', OLD.name), strftime('%Y-%m-%dT%H:%M:%fZ','now')
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_sys_tasks_before_delete
BEFORE DELETE ON sys_tasks
BEGIN
    INSERT INTO sys_activity_logs(id, project_id, task_id, actor_type, action, details_json, created_at)
    VALUES (
        lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-a' || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))),
        OLD.project_id, OLD.id, 'system', 'task.deleted', json_object('task_id', OLD.id, 'name', OLD.name), strftime('%Y-%m-%dT%H:%M:%fZ','now')
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_sys_agents_before_delete
BEFORE DELETE ON sys_agents
BEGIN
    INSERT INTO sys_activity_logs(id, agent_id, actor_type, action, details_json, created_at)
    VALUES (
        lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-a' || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))),
        OLD.id, 'system', 'agent.deleted', json_object('agent_id', OLD.id, 'name', OLD.name), strftime('%Y-%m-%dT%H:%M:%fZ','now')
    );
END;
