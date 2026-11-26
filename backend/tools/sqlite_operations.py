from __future__ import annotations

import sqlite3
import json
import time
from typing import Any

from ..database import DB_PATH

_READ_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
_WRITE_ACTIONS = {
    sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
    sqlite3.SQLITE_CREATE_INDEX, sqlite3.SQLITE_CREATE_TABLE,
    sqlite3.SQLITE_CREATE_TEMP_INDEX, sqlite3.SQLITE_CREATE_TEMP_TABLE,
    sqlite3.SQLITE_CREATE_TEMP_TRIGGER, sqlite3.SQLITE_CREATE_TEMP_VIEW,
    sqlite3.SQLITE_CREATE_TRIGGER, sqlite3.SQLITE_CREATE_VIEW,
    sqlite3.SQLITE_DROP_INDEX, sqlite3.SQLITE_DROP_TABLE,
    sqlite3.SQLITE_DROP_TEMP_INDEX, sqlite3.SQLITE_DROP_TEMP_TABLE,
    sqlite3.SQLITE_DROP_TEMP_TRIGGER, sqlite3.SQLITE_DROP_TEMP_VIEW,
    sqlite3.SQLITE_DROP_TRIGGER, sqlite3.SQLITE_DROP_VIEW,
    sqlite3.SQLITE_ALTER_TABLE, sqlite3.SQLITE_REINDEX, sqlite3.SQLITE_ANALYZE,
}


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(str(DB_PATH), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=15000")
    return connection


def query_sql(arguments: dict[str, Any]) -> dict[str, Any]:
    sql = str(arguments.get("sql") or "").strip()
    if not sql:
        raise ValueError("SQL query is required.")
    connection = _connect()
    try:
        deadline = time.monotonic() + 5.0
        connection.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
        def authorizer(action: int, arg1: str | None, arg2: str | None, db: str | None, trigger: str | None) -> int:
            return sqlite3.SQLITE_OK if action in _READ_ACTIONS else sqlite3.SQLITE_DENY
        connection.set_authorizer(authorizer)
        cursor = connection.execute(sql)
        columns = [item[0] for item in (cursor.description or [])]
        rows = [dict(row) for row in cursor.fetchmany(501)]
        truncated = len(rows) > 500
        rows = rows[:500]
        if len(json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8")) > 2_000_000:
            raise ValueError("Query result exceeds the 2 MB response limit.")
        return {"columns": columns, "rows": rows, "row_count": len(rows), "truncated": truncated, "database": DB_PATH.name}
    finally:
        connection.close()


def modify_sql(arguments: dict[str, Any]) -> dict[str, Any]:
    sql = str(arguments.get("sql") or "").strip()
    if not sql:
        raise ValueError("SQL statement is required.")
    connection = _connect()
    try:
        deadline = time.monotonic() + 5.0
        connection.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
        def authorizer(action: int, arg1: str | None, arg2: str | None, db: str | None, trigger: str | None) -> int:
            if action in _READ_ACTIONS or action in _WRITE_ACTIONS or action in {sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_SAVEPOINT}:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        connection.set_authorizer(authorizer)
        cursor = connection.execute(sql)
        affected = max(cursor.rowcount, 0)
        connection.commit()
        return {"message": "Database modification completed.", "affected_rows": affected, "database": DB_PATH.name}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def register_sqlite_operation_tools(manager: Any, *, allow_modify: bool, allow_query: bool = True) -> None:
    if allow_query:
        manager.register(
            "sqlite_query",
            "Execute one read-only SQL query against the application's configured SQLite database. Only read operations are permitted. Results are limited to 500 rows.",
            {"type": "object", "properties": {"sql": {"type": "string", "description": "A single SELECT or read-only SQL statement."}}, "required": ["sql"], "additionalProperties": False},
            query_sql,
        )
    if allow_modify:
        manager.register(
            "sqlite_modify",
            "Execute one INSERT, UPDATE, DELETE, CREATE, ALTER or DROP statement against the configured SQLite database. This changes data or schema. Never use for read-only queries. User authorisation and application policy still apply.",
            {"type": "object", "properties": {"sql": {"type": "string", "description": "One database modification statement."}}, "required": ["sql"], "additionalProperties": False},
            modify_sql,
        )
