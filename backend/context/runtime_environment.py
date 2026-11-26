"""Build a safe, current-turn environment snapshot for every AI runtime.

The snapshot contains technical configuration and capability availability only.
It deliberately excludes credentials, environment variable values, user records,
and arbitrary filesystem contents.
"""
from __future__ import annotations

import importlib.metadata
import os
import platform
import sqlite3
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..database import DB_PATH, PROJECT_ROOT
from ..capability_catalog import list_system_capabilities


def _version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _database_snapshot() -> dict[str, Any]:
    result: dict[str, Any] = {
        "engine": "SQLite",
        "path": str(DB_PATH),
        "exists": DB_PATH.is_file(),
        "journal_mode": "unknown",
        "schema_version": None,
        "tables": [],
        "inspection_status": "not_inspected",
    }
    if not DB_PATH.is_file():
        result["inspection_status"] = "database_file_missing"
        return result
    try:
        # Read-only connection: environment discovery must never create or mutate data.
        uri = DB_PATH.as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2)
        try:
            result["journal_mode"] = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).upper()
            result["schema_version"] = int(conn.execute("PRAGMA schema_version").fetchone()[0])
            result["tables"] = [
                str(row[0]) for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view') "
                    "AND name NOT LIKE 'sqlite_%' ORDER BY name"
                ).fetchall()
            ]
            result["inspection_status"] = "verified"
        finally:
            conn.close()
    except (OSError, sqlite3.Error) as exc:
        result["inspection_status"] = f"unavailable: {type(exc).__name__}"
    return result


def _endpoint_summary(base_url: str | None) -> str:
    if not base_url:
        return "not_configured"
    try:
        parsed = urlsplit(base_url)
        # Do not expose URL user-info, query strings, fragments or credentials.
        host = parsed.hostname or "unknown-host"
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{host}{port}{parsed.path}"
    except ValueError:
        return "configured_but_unparseable"


def build_runtime_environment(
    *,
    agent_id: str,
    model: str | None,
    available_tools: list[str] | None = None,
    allowed_tools: list[str] | tuple[str, ...] | None = None,
    workspace_root: str | Path | None = None,
    project_root: str | Path | None = None,
    read_enabled: bool | None = None,
    write_enabled: bool | None = None,
    ollama_base_url: str | None = None,
) -> dict[str, Any]:
    """Return a bounded, secret-free snapshot for the current AI invocation."""
    workspace = Path(workspace_root or os.getenv("AGENT_WORKSPACE", Path.home() / "AgentWorkspace")).expanduser().resolve()
    root = Path(project_root or PROJECT_ROOT).expanduser().resolve()
    return {
        "source": "backend_runtime_snapshot",
        "verified_at_invocation": True,
        "application": {
            "name": "LocalAgentUI",
            "project_root": str(PROJECT_ROOT),
            "backend_root": str(PROJECT_ROOT / "backend"),
            "runtime_os": platform.system(),
            "runtime_os_release": platform.release(),
            "python_version": platform.python_version(),
            "fastapi_version": _version("fastapi"),
        },
        "model_runtime": {
            "provider": "Ollama-compatible OpenAI API",
            "endpoint": _endpoint_summary(ollama_base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")),
            "selected_model": model or "not_selected",
        },
        "storage": {
            "database": _database_snapshot(),
            "workspace_root": str(workspace),
            "authorised_project_root": str(root),
            "workspace_read_enabled": read_enabled,
            "workspace_write_enabled": write_enabled,
        },
        "system_capabilities": [
            {
                "capability_id": item.get("capability_id"),
                "name": item.get("name"),
                "status": item.get("status"),
                "available": bool(item.get("available")),
                "scope": item.get("scope"),
            }
            for item in list_system_capabilities()
        ],
        "agent_runtime": {
            "agent_id": agent_id,
            "available_tools_this_invocation": sorted(set(available_tools or [])),
            "configured_allowed_tools": sorted(set(allowed_tools or [])),
            "tool_availability_is_invocation_scoped": True,
        },
        "security": {
            "credentials_included": False,
            "environment_variable_values_included": False,
            "user_business_records_included": False,
            "database_access": "Use registered tools and their enforced permissions; do not infer write access from database visibility.",
            "filesystem_access": "Use only tools and roots explicitly supplied for this invocation.",
        },
    }


def format_runtime_environment(snapshot: dict[str, Any]) -> str:
    """Format the snapshot as a compact, explicit system-context block."""
    import json

    return (
        "# P0.5 — Verified Runtime Environment Context\n"
        "The following snapshot is generated by the Backend for this AI invocation. "
        "Treat it as authoritative for technical environment facts, but not as permission to act. "
        "Tool availability is limited to the current invocation. Never infer hidden tools, write permissions, "
        "database records, or successful operations from this snapshot. Credentials and user business records are excluded.\n"
        "```json\n"
        + json.dumps(snapshot, ensure_ascii=False, indent=2, default=str)
        + "\n```"
    )
