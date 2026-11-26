from __future__ import annotations

from typing import Any, Iterable


# Capability IDs are stable identifiers. Tool names here are the real runtime
# permission aliases consumed by AgentRuntime, not descriptive labels.
_CAPABILITIES: list[dict[str, Any]] = [
    {
        "capability_id": "data_analysis",
        "name": "Data Analysis",
        "category": "Core",
        "description": "Inspect datasets and perform read-only analysis using the authorised local data context.",
        "status": "available",
        "available": True,
        "assignable": True,
        "grants_tools": ["sqlite_query"],
        "risk_level": "low",
        "scope": "Specialist Agent; read-only data access",
    },
    {
        "capability_id": "data_cleaning",
        "name": "Data Cleaning",
        "category": "Core",
        "description": "Read and update authorised workspace files while cleaning or transforming data.",
        "status": "available",
        "available": True,
        "assignable": True,
        "grants_tools": ["workspace_modify"],
        "risk_level": "medium",
        "scope": "Specialist Agent; authorised workspace only",
    },
    {
        "capability_id": "data_export",
        "name": "Data Export",
        "category": "Core",
        "description": "Create export files in the authorised workspace. Does not grant access outside that workspace.",
        "status": "available",
        "available": True,
        "assignable": True,
        "grants_tools": ["workspace_modify"],
        "risk_level": "medium",
        "scope": "Specialist Agent; authorised workspace only",
    },
    {
        "capability_id": "database_modification",
        "name": "Database Modification",
        "category": "Controlled",
        "description": "Modify local SQLite records or schema. Grant only when a Specialist has a specific approved need.",
        "status": "available",
        "available": True,
        "assignable": True,
        "grants_tools": ["sqlite_modify"],
        "risk_level": "high",
        "scope": "Specialist Agent; explicit assignment required",
    },
    {
        "capability_id": "workspace_file_management",
        "name": "Workspace File Management",
        "category": "Core",
        "description": "Create, write, copy, move and rename files within the authorised workspace. Delete remains unavailable to Specialists.",
        "status": "available",
        "available": True,
        "assignable": True,
        "grants_tools": ["workspace_modify"],
        "risk_level": "medium",
        "scope": "Specialist Agent; authorised workspace only",
    },
    {
        "capability_id": "web_search",
        "name": "Web Search",
        "category": "Optional",
        "description": "Search the public web through a configured provider. Specialist runtime integration is not enabled yet.",
        "status": "planned",
        "available": False,
        "assignable": False,
        "grants_tools": [],
        "risk_level": "medium",
        "scope": "Main Agent only until Specialist integration is implemented",
    },
    {
        "capability_id": "ocr",
        "name": "OCR",
        "category": "Optional",
        "description": "Extract text from images and scanned documents.",
        "status": "planned",
        "available": False,
        "assignable": False,
        "grants_tools": [],
        "risk_level": "low",
        "scope": "Future Agent assignment",
    },
    {
        "capability_id": "pdf_processing",
        "name": "PDF Processing",
        "category": "Optional",
        "description": "Read, parse and extract structured content from PDF files.",
        "status": "planned",
        "available": False,
        "assignable": False,
        "grants_tools": [],
        "risk_level": "low",
        "scope": "Future Agent assignment",
    },
    {
        "capability_id": "excel_processing",
        "name": "Excel Processing",
        "category": "Optional",
        "description": "Read, transform and generate Excel workbooks. A dedicated binary workbook executor is not registered.",
        "status": "planned",
        "available": False,
        "assignable": False,
        "grants_tools": [],
        "risk_level": "low",
        "scope": "Future Agent assignment",
    },
    {
        "capability_id": "image_processing",
        "name": "Image Processing",
        "category": "Optional",
        "description": "Resize, convert, compress and inspect image files.",
        "status": "planned",
        "available": False,
        "assignable": False,
        "grants_tools": [],
        "risk_level": "low",
        "scope": "Future Agent assignment",
    },
    {
        "capability_id": "python_execution",
        "name": "Python Execution",
        "category": "Optional",
        "description": "Run Python tasks in a controlled isolated environment.",
        "status": "planned",
        "available": False,
        "assignable": False,
        "grants_tools": [],
        "risk_level": "high",
        "scope": "Future Agent assignment",
    },
    {
        "capability_id": "archive_management",
        "name": "Archive Management",
        "category": "Optional",
        "description": "Create and extract ZIP archives with path validation.",
        "status": "planned",
        "available": False,
        "assignable": False,
        "grants_tools": [],
        "risk_level": "medium",
        "scope": "Future Agent assignment",
    },
]


def list_system_capabilities() -> list[dict[str, Any]]:
    return [dict(item, grants_tools=list(item["grants_tools"])) for item in _CAPABILITIES]


def get_assignable_capability_ids() -> set[str]:
    return {item["capability_id"] for item in _CAPABILITIES if item["assignable"]}


def resolve_agent_tool_permissions(
    capabilities: Iterable[str] = (),
    direct_tools: Iterable[str] = (),
    denied_tools: Iterable[str] = (),
) -> dict[str, list[str]]:
    by_id = {item["capability_id"]: item for item in _CAPABILITIES}
    inherited: set[str] = set()
    for capability_id in capabilities:
        item = by_id.get(str(capability_id))
        if item and item["assignable"]:
            inherited.update(item["grants_tools"])
    direct = {str(name) for name in direct_tools if str(name)}
    denied = {str(name) for name in denied_tools if str(name)}
    effective = (inherited | direct) - denied
    return {
        "inherited_tools": sorted(inherited - denied),
        "direct_tools": sorted(direct - denied),
        "denied_tools": sorted(denied),
        "effective_tools": sorted(effective),
    }
