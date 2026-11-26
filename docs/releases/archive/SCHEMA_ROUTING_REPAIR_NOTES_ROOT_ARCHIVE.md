# Database Schema Routing Repair

## Changes

- Kept the existing Main Agent database-intent detection and preflight flow. The uploaded `backend/main.py` already uses correctly bounded `\b` regular expressions for English schema keywords; it does not contain the earlier over-escaped `\\b` regression.
- Updated `backend/tools/database_tools.py` so table metadata, CREATE DDL, and foreign-key relationship results are all derived from one schema snapshot per tool call. This prevents the reported database identity/schema version from coming from a different cache refresh than the actual table/relationship payload.
- Added `backend/tests/test_database_schema_routing.py` to protect English and Chinese intent detection, table-specific tool routing, real schema counts, DDL retrieval, and explicit missing-table errors.

## Validation against the included SQLite database

- User tables: 13
- `projects`: 13 columns
- `tasks`: 21 columns
- `agents`: 10 columns
- Declared foreign-key definitions: 23

## Checks run

- `python -m unittest backend.tests.test_database_schema_routing -v` — 5 tests passed.
- `python -m compileall -q backend` — passed.

The database tools remain read-only. No database records or schema definitions were modified.
