from __future__ import annotations

import unittest
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from backend.intent_router import classify_intent
from backend.main import _management_tool_schemas, _needs_database_tools, _needs_database_modify, _needs_search_tools, _needs_workspace_file_tools
from backend.agents.agent_registry import AgentDefinition
from backend.agents.agent_runtime import AgentRuntime


class SystemCapabilityPolicyTests(unittest.TestCase):
    def test_management_read_only_schema_excludes_mutations(self):
        names = {item["function"]["name"] for item in _management_tool_schemas(include_mutations=False)}
        self.assertEqual(names, {"list_projects", "list_available_agents", "list_project_tasks"})

    def test_management_main_agent_schema_includes_mutations(self):
        names = {item["function"]["name"] for item in _management_tool_schemas(include_mutations=True)}
        self.assertIn("create_project_task", names)
        self.assertIn("assign_task_agent", names)
        self.assertIn("update_project_task", names)

    def test_database_query_and_modify_detection(self):
        self.assertTrue(_needs_database_tools("SELECT name FROM sys_projects"))
        self.assertTrue(_needs_database_modify("UPDATE sys_projects SET name = 'x'"))
        self.assertFalse(_needs_database_modify("Show me the database schema"))

    def test_search_and_file_capability_detection(self):
        self.assertTrue(_needs_search_tools("Search the web for latest Python release"))
        self.assertTrue(_needs_workspace_file_tools("List files in the workspace"))

    def test_search_is_tool_query(self):
        decision = classify_intent("Search the web for latest Python release", web_search=True)
        self.assertEqual(decision.mode, "tool_query")
        self.assertTrue(decision.web_search)

    def test_specialist_runtime_defaults_to_query_and_read_only_file_access(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            project_root = root / "project"
            workspace.mkdir()
            project_root.mkdir()
            (workspace / ".agent_state").mkdir()
            (workspace / ".agent_state" / "project_permissions.json").write_text(json.dumps({"project_root": str(project_root), "read_enabled": True, "write_enabled": True}), encoding="utf-8")
            agent = AgentDefinition("qa_agent", "QA Agent", "test role", "test", model="test", allowed_tools=())
            with patch.dict(os.environ, {"AGENT_WORKSPACE": str(workspace)}):
                manager = AgentRuntime("http://localhost:11434/v1", "test")._tool_manager(agent)
            names = set(manager.names())
            self.assertIn("sqlite_query", names)
            self.assertNotIn("sqlite_modify", names)
            self.assertIn("workspace_read", names)
            self.assertNotIn("workspace_write", names)

    def test_specialist_runtime_grants_modify_only_when_explicitly_allowed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            project_root = root / "project"
            workspace.mkdir(); project_root.mkdir(); (workspace / ".agent_state").mkdir()
            (workspace / ".agent_state" / "project_permissions.json").write_text(json.dumps({"project_root": str(project_root), "read_enabled": True, "write_enabled": True}), encoding="utf-8")
            agent = AgentDefinition("developer", "Developer", "test role", "test", model="test", allowed_tools=("sqlite_modify", "workspace_modify"))
            with patch.dict(os.environ, {"AGENT_WORKSPACE": str(workspace)}):
                manager = AgentRuntime("http://localhost:11434/v1", "test")._tool_manager(agent)
            names = set(manager.names())
            self.assertIn("sqlite_modify", names)
            self.assertIn("workspace_write", names)
            self.assertNotIn("workspace_delete", names)

    def test_project_and_database_modes_do_not_delegate_automatically(self):
        decision = classify_intent("List project tasks and inspect table schema", project_tools=True, database_tools=True)
        self.assertEqual(decision.mode, "tool_query")
        self.assertFalse(decision.allow_agent_delegation)


if __name__ == "__main__":
    unittest.main()
