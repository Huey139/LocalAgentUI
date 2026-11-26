from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from ..database import DB_PATH, connect
from .migration_manager import apply_pending_migrations
from .schema_validator import validate_database
from .seed_manager import seed_defaults

LEGACY_TABLES = {
    "agents", "projects", "project_proposals", "tasks", "task_assignments",
    "task_dependencies", "task_executions", "progress_records", "risks",
    "decisions", "deliverables", "test_records", "activity_logs",
}


def _existing_user_tables(conn: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()}


def initialize_database() -> dict[str, object]:
    """Apply migrations, seed defaults, and validate before the API starts serving."""
    with connect() as conn:
        existing = _existing_user_tables(conn)
        if existing & LEGACY_TABLES and "sys_schema_migrations" not in existing:
            raise RuntimeError(
                "A legacy prototype database was detected. The v2.0 schema is a clean rebuild. "
                "Run `python -m backend.db.bootstrap --reset-prototype` once to replace the prototype database."
            )
        apply_pending_migrations(conn)
        seed_defaults(conn)
        return validate_database(conn)


def reset_prototype_database() -> dict[str, object]:
    """Explicitly replace the prototype DB; never called during normal startup."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(DB_PATH) + suffix)
        if path.exists():
            path.unlink()
    return initialize_database()


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Agent database bootstrap")
    parser.add_argument("--reset-prototype", action="store_true", help="Delete the legacy prototype database and initialise Schema v2.0")
    args = parser.parse_args()
    result = reset_prototype_database() if args.reset_prototype else initialize_database()
    print(f"Database ready: schema v{result['schema_version']}, {result['table_count']} tables at {DB_PATH}")


if __name__ == "__main__":
    main()
