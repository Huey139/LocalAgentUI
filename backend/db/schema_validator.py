from __future__ import annotations

import sqlite3

EXPECTED_TABLES = {
    "sys_agents", "sys_projects", "sys_project_proposals", "sys_tasks",
    "sys_task_assignments", "sys_task_dependencies", "sys_task_executions",
    "sys_progress_records", "sys_risks", "sys_decisions", "sys_deliverables",
    "sys_test_records", "sys_approval_requests", "sys_project_lifecycle", "sys_tools", "sys_tool_versions",
    "sys_agent_tools", "sys_tool_executions", "sys_activity_logs", "sys_schema_migrations", "sys_team_plans",
    "sys_business_contexts", "sys_workspaces", "sys_artifacts", "sys_execution_evidence",
}


from .migration_manager import MIGRATIONS
LATEST_SCHEMA_VERSION = max((migration.VERSION for migration in MIGRATIONS), default=0)


class SchemaValidationError(RuntimeError):
    pass


def validate_database(conn: sqlite3.Connection) -> dict[str, object]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    actual = {str(row[0]) for row in rows}
    missing = sorted(EXPECTED_TABLES - actual)
    unexpected = sorted(name for name in actual if not name.startswith("sys_"))
    if missing:
        raise SchemaValidationError(f"Database schema is incomplete; missing tables: {', '.join(missing)}")
    if unexpected:
        raise SchemaValidationError(f"Legacy or non-system tables remain: {', '.join(unexpected)}")
    version = conn.execute("SELECT COALESCE(MAX(version),0) FROM sys_schema_migrations").fetchone()[0]
    if int(version) != LATEST_SCHEMA_VERSION:
        raise SchemaValidationError(
            f"Database schema version {version} does not match the latest supported version {LATEST_SCHEMA_VERSION}."
        )
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise SchemaValidationError(f"SQLite integrity check failed: {integrity}")
    foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise SchemaValidationError(f"Foreign key validation failed for {len(foreign_key_errors)} row(s).")
    return {"valid": True, "schema_version": int(version), "table_count": len(actual), "tables": sorted(actual)}
