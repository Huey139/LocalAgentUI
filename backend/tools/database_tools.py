from __future__ import annotations

from typing import Any

from ..services.database_schema_service import DatabaseSchemaService
from .tool_manager import ToolManager


_SCHEMA = DatabaseSchemaService()


def _require_table_name(arguments: dict[str, Any]) -> str:
    value = arguments.get("table_name")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A non-empty string 'table_name' is required.")
    return value.strip()


def _schema_metadata(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "database": schema.get("database"),
        "database_path": schema.get("database_path"),
        "schema_version": schema.get("schema_version"),
        "application_schema_version": schema.get("application_schema_version", 0),
        "table_count": schema.get("table_count", len(schema.get("tables", []))),
    }


def _list_tables(_: dict[str, Any]) -> dict[str, Any]:
    """Return the complete user-table/view inventory from one schema snapshot."""
    schema = _SCHEMA.get_schema()
    tables = schema.get("tables", [])
    return {
        **_schema_metadata(schema),
        "source": "sqlite_master",
        "verified": True,
        "tables": [
            {
                "name": table["name"],
                "type": table["type"],
                "column_count": len(table.get("columns", [])),
                "foreign_key_count": len(table.get("foreign_keys", [])),
                "index_count": len(table.get("indexes", [])),
            }
            for table in tables
        ],
    }


def _find_table_in_snapshot(
    schema: dict[str, Any], table_name: str
) -> dict[str, Any]:
    """Resolve a table against the exact schema snapshot used by this tool call."""
    requested = table_name.strip()
    if not requested:
        raise ValueError("A non-empty string 'table_name' is required.")

    for table in schema.get("tables", []):
        if table.get("name", "").casefold() == requested.casefold():
            return table

    available = ", ".join(
        item.get("name", "")
        for item in schema.get("tables", [])
        if item.get("name")
    )
    raise ValueError(
        f"Unknown table or view '{requested}'. Available: {available or '(none)'}"
    )


def _get_table(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return complete structured metadata for one existing table or view."""
    table_name = _require_table_name(arguments)
    schema = _SCHEMA.get_schema()
    table = _find_table_in_snapshot(schema, table_name)

    return {
        **_schema_metadata(schema),
        "table_name": table["name"],
        "object_type": table["type"],
        "source": "sqlite_master_and_sqlite_pragma",
        "verified": True,
        "column_count": len(table.get("columns", [])),
        "foreign_key_count": len(table.get("foreign_keys", [])),
        "index_count": len(table.get("indexes", [])),
        "columns": table.get("columns", []),
        "foreign_keys": table.get("foreign_keys", []),
        "indexes": table.get("indexes", []),
        # Exact DDL is included for constraints not fully represented by PRAGMA.
        "create_sql": table.get("definition"),
    }


def _get_table_definition(arguments: dict[str, Any]) -> dict[str, Any]:
    table_name = _require_table_name(arguments)
    schema = _SCHEMA.get_schema()
    table = _find_table_in_snapshot(schema, table_name)
    definition = table.get("definition")
    if not definition:
        raise ValueError(
            f"SQLite does not store a CREATE definition for '{table['name']}'."
        )
    result = {
        "table_name": table["name"],
        "object_type": table["type"],
        "create_sql": definition,
        "source": "sqlite_master.sql",
        "verified": True,
    }
    return {
        **_schema_metadata(schema),
        **result,
    }


def _relationships(_: dict[str, Any]) -> dict[str, Any]:
    schema = _SCHEMA.get_schema()
    relationships = [
        {
            "from_table": table["name"],
            "from_column": fk["column"],
            "to_table": fk["referenced_table"],
            "to_column": fk["referenced_column"],
            "on_update": fk["on_update"],
            "on_delete": fk["on_delete"],
            "foreign_key_id": fk["id"],
            "sequence": fk["sequence"],
            "match": fk["match"],
        }
        for table in schema.get("tables", [])
        for fk in table.get("foreign_keys", [])
    ]
    return {
        **_schema_metadata(schema),
        "source": "sqlite_pragma_foreign_key_list",
        "verified": True,
        "relationship_count": len(relationships),
        "relationships": relationships,
    }


def _refresh(_: dict[str, Any]) -> dict[str, Any]:
    schema = _SCHEMA.refresh()
    return {
        **_schema_metadata(schema),
        "source": "sqlite_master_and_sqlite_pragma",
        "verified": True,
        "message": "Schema cache refreshed.",
    }


def register_database_tools(manager: ToolManager) -> None:
    manager.register(
        "list_database_tables",
        (
            "List every user-defined table and view in the connected local SQLite "
            "database. Returns the complete inventory, object types, column counts, "
            "foreign-key counts, index counts, database path and schema version. "
            "Read-only metadata; use this before referring to table names."
        ),
        {"type": "object", "properties": {}, "required": []},
        _list_tables,
    )
    manager.register(
        "get_table_schema",
        (
            "Return complete structured metadata for one existing SQLite table or "
            "view: every column (including hidden/generated columns where exposed), "
            "declared type, nullability, default, primary-key position, all declared "
            "foreign keys, index definitions and the exact stored CREATE SQL. "
            "Use the exact table/view name from list_database_tables. Read-only."
        ),
        {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "minLength": 1},
            },
            "required": ["table_name"],
            "additionalProperties": False,
        },
        _get_table,
    )
    manager.register(
        "get_table_definition",
        (
            "Return the exact CREATE TABLE or CREATE VIEW SQL stored in SQLite "
            "sqlite_master for one named object. Use this to inspect explicitly "
            "declared CHECK, UNIQUE, DEFAULT, PRIMARY KEY, FOREIGN KEY and other "
            "DDL constraints. The SQL is returned verbatim and is not executed. "
            "Read-only metadata access."
        ),
        {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "minLength": 1},
            },
            "required": ["table_name"],
            "additionalProperties": False,
        },
        _get_table_definition,
    )
    manager.register(
        "get_table_relationships",
        (
            "Return every declared foreign-key relationship across all user-defined "
            "tables and views, including source table/column, referenced table/column, "
            "update/delete actions and relationship count. This reports declared "
            "foreign keys, not inferred logical relationships. Read-only metadata."
        ),
        {"type": "object", "properties": {}, "required": []},
        _relationships,
    )
    manager.register(
        "refresh_database_schema",
        (
            "Force a fresh read of SQLite schema metadata and replace the in-memory "
            "schema cache. Does not modify database records or schema."
        ),
        {"type": "object", "properties": {}, "required": []},
        _refresh,
    )
