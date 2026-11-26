from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.capability_catalog import resolve_agent_tool_permissions
from backend.agents.agent_registry import AgentDefinition
from backend.agents.agent_runtime import AgentRuntime
from backend.agents.agent_registry import AgentRegistry


class CapabilityPermissionResolutionTests(unittest.TestCase):
    def test_capability_tools_and_direct_tools_are_merged(self):
        result = resolve_agent_tool_permissions(
            ["database_modification", "workspace_file_management"],
            ["external_lookup"],
        )
        self.assertEqual(set(result["inherited_tools"]), {"sqlite_modify", "workspace_modify"})
        self.assertEqual(set(result["direct_tools"]), {"external_lookup"})
        self.assertEqual(set(result["effective_tools"]), {"sqlite_modify", "workspace_modify", "external_lookup"})

    def test_explicit_deny_overrides_capability_and_direct_grant(self):
        result = resolve_agent_tool_permissions(
            ["database_modification"], ["sqlite_modify"], ["sqlite_modify"]
        )
        self.assertNotIn("sqlite_modify", result["effective_tools"])
        self.assertIn("sqlite_modify", result["denied_tools"])

    def test_unavailable_legacy_capability_grants_no_tools(self):
        result = resolve_agent_tool_permissions(["ocr", "old free text label"], [], [])
        self.assertEqual(result["effective_tools"], [])

    def test_agent_registry_persists_capabilities_direct_and_denied_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "agents.json"
            role_dir = Path(__file__).parent / "prompts" / "roles"
            registry = AgentRegistry(role_directory=role_dir, config_path=config)
            created = registry.create_custom({
                "display_name": "Capability Test Agent",
                "role_prompt": "Test role",
                "model": "test-model",
                "capabilities": ["database_modification"],
                "capability_notes": ["legacy descriptive skill"],
                "allowed_tools": ["external_lookup"],
                "denied_tools": ["sqlite_modify"],
            })
            self.assertIn("database_modification", created["capabilities"])
            self.assertIn("sqlite_modify", created["denied_tools"])
            self.assertNotIn("sqlite_modify", created["effective_tools"])
            self.assertIn("external_lookup", created["effective_tools"])
            self.assertEqual(created["capability_notes"], ["legacy descriptive skill"])


class AgentRuntimeCapabilityTests(unittest.TestCase):
    def test_capability_grants_sqlite_modify_tool(self):
        agent = AgentDefinition(
            "developer", "Developer", "role", "test",
            capabilities=("database_modification",),
        )
        manager = AgentRuntime("http://localhost:11434/v1", "test")._tool_manager(agent)
        self.assertIn("sqlite_query", manager.names())
        self.assertIn("sqlite_modify", manager.names())

    def test_explicit_deny_removes_default_read_tool(self):
        agent = AgentDefinition(
            "qa_agent", "QA", "role", "test", denied_tools=("sqlite_query",),
        )
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            (workspace / ".agent_state").mkdir()
            with patch.dict(os.environ, {"AGENT_WORKSPACE": str(workspace)}):
                manager = AgentRuntime("http://localhost:11434/v1", "test")._tool_manager(agent)
        self.assertNotIn("sqlite_query", manager.names())

    def test_workspace_capability_grants_write_tools_but_deny_overrides(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            state = workspace / ".agent_state"
            state.mkdir()
            project_root = workspace / "project"
            project_root.mkdir()
            (state / "project_permissions.json").write_text(json.dumps({
                "project_root": str(project_root), "read_enabled": True, "write_enabled": True,
            }), encoding="utf-8")
            with patch.dict(os.environ, {"AGENT_WORKSPACE": str(workspace)}):
                allowed = AgentRuntime("http://localhost:11434/v1", "test")._tool_manager(
                    AgentDefinition("analyst", "Analyst", "role", "test", capabilities=("data_export",))
                )
                denied = AgentRuntime("http://localhost:11434/v1", "test")._tool_manager(
                    AgentDefinition("analyst", "Analyst", "role", "test", capabilities=("data_export",), denied_tools=("workspace_modify",))
                )
        self.assertIn("workspace_write", allowed.names())
        self.assertNotIn("workspace_write", denied.names())


if __name__ == "__main__":
    unittest.main()
