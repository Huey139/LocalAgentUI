from __future__ import annotations

import copy
import threading
import time
from typing import Any

from ..database import DB_PATH, connect


class DatabaseSchemaService:
    """Read-only SQLite schema inspection with a version-aware in-memory cache."""

    def __init__(self, cache_ttl_seconds: int = 30) -> None:
        self.cache_ttl_seconds = max(0, cache_ttl_seconds)
        self._cache: dict[str, Any] | None = None
        self._schema_version: int | None = None
        self._cached_at = 0.0
        self._lock = threading.RLock()

    @staticmethod
    def _quote(identifier: str) -> str:
        """Quote a SQLite identifier without allowing SQL injection."""
        return '"' + identifier.replace('"', '""') + '"'

    @staticmethod
    def _row_value(row: Any, key: str, default: Any = None) -> Any:
        try:
            return row[key]
        except (KeyError, IndexError, TypeError):
            return default

    def _load(self) -> dict[str, Any]:
        database_path = str(DB_PATH)
        with connect() as conn:
            # SQLite's schema_version is an internal schema cookie used for cache
            # invalidation; the application migration version is tracked separately.
            version = int(conn.execute("PRAGMA schema_version").fetchone()[0])
            migration_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sys_schema_migrations'"
            ).fetchone()
            application_version = 0
            if migration_table:
                application_version = int(conn.execute(
                    "SELECT COALESCE(MAX(version), 0) FROM sys_schema_migrations"
                ).fetchone()[0])
            objects = conn.execute(
                """
                SELECT name, type, sql
                FROM sqlite_master
                WHERE type IN ('table', 'view')
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY type, name
                """
            ).fetchall()

            tables: list[dict[str, Any]] = []
            for obj in objects:
                name = str(obj["name"])
                object_type = str(obj["type"])
                qname = self._quote(name)

                # table_xinfo includes generated/hidden columns that table_info omits.
                raw_columns = conn.execute(
                    f"PRAGMA table_xinfo({qname})"
                ).fetchall()
                columns = [
                    {
                        "name": c["name"],
                        "type": c["type"] or "UNDECLARED",
                        "not_null": bool(c["notnull"]),
                        "default": c["dflt_value"],
                        "primary_key_position": int(c["pk"]),
                        "hidden": int(self._row_value(c, "hidden", 0) or 0),
                    }
                    for c in raw_columns
                ]

                raw_foreign_keys = conn.execute(
                    f"PRAGMA foreign_key_list({qname})"
                ).fetchall()
                foreign_keys = [
                    {
                        "id": int(f["id"]),
                        "sequence": int(f["seq"]),
                        "column": f["from"],
                        "referenced_table": f["table"],
                        "referenced_column": f["to"],
                        "on_update": f["on_update"],
                        "on_delete": f["on_delete"],
                        "match": self._row_value(f, "match", "NONE"),
                    }
                    for f in raw_foreign_keys
                ]

                raw_indexes = conn.execute(
                    f"PRAGMA index_list({qname})"
                ).fetchall()
                indexes: list[dict[str, Any]] = []
                for index in raw_indexes:
                    index_name = str(index["name"])
                    qindex = self._quote(index_name)
                    index_columns = conn.execute(
                        f"PRAGMA index_xinfo({qindex})"
                    ).fetchall()
                    index_sql_row = conn.execute(
                        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
                        (index_name,),
                    ).fetchone()
                    indexes.append(
                        {
                            "name": index_name,
                            "unique": bool(index["unique"]),
                            "origin": index["origin"],
                            "partial": bool(index["partial"]),
                            "columns": [
                                {
                                    "sequence": int(c["seqno"]),
                                    "column_id": int(c["cid"]),
                                    "name": c["name"],
                                    "descending": bool(c["desc"]),
                                    "collation": c["coll"],
                                    "key": bool(c["key"]),
                                }
                                for c in index_columns
                            ],
                            "definition": (
                                index_sql_row["sql"] if index_sql_row else None
                            ),
                        }
                    )

                tables.append(
                    {
                        "name": name,
                        "type": object_type,
                        "columns": columns,
                        "foreign_keys": foreign_keys,
                        "indexes": indexes,
                        # Preserve SQLite's stored DDL verbatim. CHECK, UNIQUE,
                        # DEFAULT and table-level constraints are not fully
                        # represented by PRAGMA table_info.
                        "definition": obj["sql"],
                    }
                )

        return {
            "database": "sqlite",
            "database_path": database_path,
            "schema_version": version,
            "application_schema_version": application_version,
            "table_count": len(tables),
            "tables": tables,
        }

    def get_schema(self, force_refresh: bool = False) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            try:
                with connect() as conn:
                    current_version = int(
                        conn.execute("PRAGMA schema_version").fetchone()[0]
                    )
            except Exception:
                # Do not silently treat a failed version check as a valid cache hit.
                current_version = None

            expired = (
                self.cache_ttl_seconds == 0
                or now - self._cached_at > self.cache_ttl_seconds
            )
            refresh_required = (
                self._cache is None
                or force_refresh
                or current_version is None
                or current_version != self._schema_version
                or expired
            )
            if refresh_required:
                self._cache = self._load()
                self._schema_version = self._cache["schema_version"]
                self._cached_at = now

            # Return a defensive copy so callers cannot mutate the shared cache.
            return copy.deepcopy(self._cache)

    def get_table(self, table_name: str) -> dict[str, Any]:
        requested = table_name.strip()
        if not requested:
            raise ValueError("table_name is required")

        schema = self.get_schema()
        for table in schema["tables"]:
            if table["name"].casefold() == requested.casefold():
                return table

        names = ", ".join(t["name"] for t in schema["tables"])
        raise ValueError(
            f"Unknown table or view '{requested}'. Available: {names or '(none)'}"
        )

    def get_table_definition(self, table_name: str) -> dict[str, Any]:
        """Return the exact CREATE TABLE/VIEW SQL stored by SQLite."""
        table = self.get_table(table_name)
        definition = table.get("definition")
        if not definition:
            raise ValueError(
                f"SQLite does not store a CREATE definition for '{table['name']}'."
            )
        return {
            "table_name": table["name"],
            "object_type": table["type"],
            "create_sql": definition,
            "source": "sqlite_master.sql",
            "verified": True,
        }

    def get_relationships(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for table in self.get_schema()["tables"]:
            for fk in table["foreign_keys"]:
                result.append(
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
                )
        return result

    def refresh(self) -> dict[str, Any]:
        return self.get_schema(force_refresh=True)
