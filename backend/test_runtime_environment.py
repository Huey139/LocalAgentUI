import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.context.runtime_environment import build_runtime_environment, format_runtime_environment
from backend.prompts.prompt_manager import assemble_runtime_prompt


class RuntimeEnvironmentTests(unittest.TestCase):
    def test_snapshot_contains_environment_and_invocation_scoped_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "runtime.db"
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE sample_table (id INTEGER PRIMARY KEY)")
            conn.close()
            with patch("backend.context.runtime_environment.DB_PATH", db_path):
                snapshot = build_runtime_environment(
                    agent_id="data_analyst",
                    model="local-test-model",
                    available_tools=["sqlite_query"],
                    allowed_tools=["sqlite_query", "workspace_modify"],
                    workspace_root=tmp,
                    project_root=tmp,
                    read_enabled=True,
                    write_enabled=False,
                    ollama_base_url="http://localhost:11434/v1",
                )
        self.assertEqual(snapshot["storage"]["database"]["inspection_status"], "verified")
        self.assertIn("sample_table", snapshot["storage"]["database"]["tables"])
        self.assertEqual(snapshot["agent_runtime"]["available_tools_this_invocation"], ["sqlite_query"])
        self.assertFalse(snapshot["storage"]["workspace_write_enabled"])
        self.assertFalse(snapshot["security"]["credentials_included"])

    def test_snapshot_does_not_expose_environment_secret_values(self):
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "secret-test-value", "OLLAMA_BASE_URL": "http://user:pass@localhost:11434/v1"}):
            snapshot = build_runtime_environment(agent_id="main_agent", model="qwen-test")
        rendered = format_runtime_environment(snapshot)
        self.assertNotIn("secret-test-value", rendered)
        self.assertNotIn("user:pass", rendered)
        self.assertNotIn("SERPAPI_API_KEY", rendered)

    def test_shared_prompt_includes_runtime_environment_for_any_agent(self):
        snapshot = build_runtime_environment(
            agent_id="qa_agent", model="qwen-test", available_tools=["workspace_read"]
        )
        prompt = assemble_runtime_prompt(
            agent_id="qa_agent",
            agent_role_prompt="QA role",
            runtime_environment=snapshot,
        )
        self.assertIn("# P0.5 — Verified Runtime Environment Context", prompt)
        self.assertIn('"agent_id": "qa_agent"', prompt)
        self.assertIn('"workspace_read"', prompt)


if __name__ == "__main__":
    unittest.main()
