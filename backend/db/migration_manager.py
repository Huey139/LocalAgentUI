from __future__ import annotations

import hashlib
import sqlite3
import time

from .migrations import v001_initial_schema, v002_project_lifecycle, v003_independent_team_plans, v004_context_workspaces_artifacts
from ..database import now_iso

MIGRATIONS = [v001_initial_schema, v002_project_lifecycle, v003_independent_team_plans, v004_context_workspaces_artifacts]


def _execute_script_transactionally(conn: sqlite3.Connection, script: str) -> None:
    """Execute a SQL script statement-by-statement without executescript's implicit COMMIT."""
    statement = ""
    for line in script.splitlines():
        statement += line + "\n"
        if sqlite3.complete_statement(statement):
            sql = statement.strip()
            if sql:
                conn.execute(sql)
            statement = ""
    if statement.strip():
        raise RuntimeError("Incomplete SQL statement in migration script.")


def ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sys_schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            execution_time_ms INTEGER NOT NULL DEFAULT 0 CHECK (execution_time_ms >= 0)
        )
    """)


def current_version(conn: sqlite3.Connection) -> int:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sys_schema_migrations'"
    ).fetchone()
    if not exists:
        return 0
    row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM sys_schema_migrations").fetchone()
    return int(row[0])


def apply_pending_migrations(conn: sqlite3.Connection) -> int:
    ensure_migration_table(conn)
    applied_version = current_version(conn)
    latest_supported = max((migration.VERSION for migration in MIGRATIONS), default=0)
    if applied_version > latest_supported:
        raise RuntimeError(
            f"Database schema version {applied_version} is newer than this application supports."
        )
    for migration in MIGRATIONS:
        if migration.VERSION <= applied_version:
            recorded = conn.execute(
                "SELECT checksum FROM sys_schema_migrations WHERE version=?",
                (migration.VERSION,),
            ).fetchone()
            expected = hashlib.sha256(migration.load_sql().encode("utf-8")).hexdigest()
            if not recorded or recorded["checksum"] != expected:
                raise RuntimeError(
                    f"Migration checksum mismatch for schema version {migration.VERSION}. "
                    "Do not edit an applied migration; create a new migration version."
                )
            continue
        sql = migration.load_sql()
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        started = time.perf_counter()
        conn.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_transactionally(conn, sql)
            elapsed_ms = max(0, int((time.perf_counter() - started) * 1000))
            conn.execute(
                "INSERT INTO sys_schema_migrations(version,name,checksum,applied_at,execution_time_ms) VALUES(?,?,?,?,?)",
                (migration.VERSION, migration.NAME, checksum, now_iso(), elapsed_ms),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied_version = migration.VERSION
    return applied_version
