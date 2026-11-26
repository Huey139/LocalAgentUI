from __future__ import annotations

import sqlite3

from ..database import new_id, now_iso

DEFAULT_AGENTS = [
    ("Main Agent", "main_agent", "Team Lead and project manager", "Coordinate projects, plan work, assign specialists, monitor progress and report to the user.", '["project:read","project:write","task:read","task:write","agent:read","agent:assign"]'),
    ("Developer", "developer", "Software development", "Implement and maintain application code.", '["workspace:read","workspace:write","code:test"]'),
    ("SQL Agent", "sql_agent", "Database and SQL", "Design schemas, write SQL and inspect database behaviour.", '["database:read","database:write"]'),
    ("Data Analyst", "data_analyst", "Data analysis", "Explore data, build analyses and communicate findings.", '["workspace:read","data:analysis"]'),
    ("QA Agent", "qa_agent", "Quality assurance", "Independently test deliverables and report defects.", '["workspace:read","test:run","qa:report"]'),
    ("Research Agent", "research_agent", "Research", "Find and synthesize relevant information.", '["web:search","workspace:read"]'),
    ("File Manager", "file_manager", "Workspace file management", "Organize and manage permitted workspace files.", '["workspace:read","workspace:write"]'),
]


def seed_defaults(conn: sqlite3.Connection) -> None:
    stamp = now_iso()
    for name, role, description, prompt, permissions in DEFAULT_AGENTS:
        conn.execute(
            """INSERT OR IGNORE INTO sys_agents
            (id,name,role,description,system_prompt,permissions_json,is_builtin,created_at,updated_at)
            VALUES(?,?,?,?,?,?,1,?,?)""",
            (new_id(), name, role, description, prompt, permissions, stamp, stamp),
        )
