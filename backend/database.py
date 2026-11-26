"""SQLite connection boundary for Local Agent.

Schema ownership lives in backend.db: migrations, validation and seed data are
kept separate from connection management.
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

DB_PATH = Path(
    os.getenv("LOCAL_AGENT_DB_PATH", str(PROJECT_ROOT / "data" / "local_agent.db"))
).expanduser().resolve()
SQLITE_TIMEOUT_SECONDS = 15


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return str(uuid.uuid4())


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a configured connection and commit or roll back its unit of work."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        str(DB_PATH),
        timeout=SQLITE_TIMEOUT_SECONDS,
        isolation_level="DEFERRED",
    )
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> dict[str, object]:
    """Bootstrap the versioned schema and validate it before serving requests."""
    from .db.bootstrap import initialize_database as bootstrap

    return bootstrap()


def table_names() -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    return [str(row[0]) for row in rows]
