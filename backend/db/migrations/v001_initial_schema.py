from __future__ import annotations

from pathlib import Path

VERSION = 1
NAME = "initial_schema_v2"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "schema_v2.sql"


def load_sql() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")
