from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.tools.tool_registry import ToolRegistry
from backend.tools.tool_manager import ToolManager


class ToolRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.registry = ToolRegistry(Path(self.temp.name) / "tools.json")
        self.payload = {
            "name": "Example Search", "description": "Search public information",
            "category": "search", "endpoint": "https://example.com/search", "method": "GET",
            "parameters": {"q": {"type": "string", "description": "Query"}}, "required": ["q"],
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_crud_and_system_generated_id(self):
        with patch.object(ToolRegistry, "_validate_endpoint", side_effect=lambda value: value):
            created = self.registry.create(self.payload)
            self.assertTrue(created["tool_id"].startswith("tool_"))
            self.assertFalse(created["enabled"])
            updated = self.registry.update(created["tool_id"], {**self.payload, "name": "Example Search Updated"})
            self.assertEqual(updated["function_name"], created["function_name"])
            self.assertEqual(updated["version"], 2)
            self.registry.set_enabled(created["tool_id"], True)
            self.assertTrue(self.registry.get(created["tool_id"])["enabled"])
            self.registry.delete(created["tool_id"])
            self.assertEqual(self.registry.list_tools(), [])

    def test_rejects_non_https_and_private_hosts(self):
        with self.assertRaises(ValueError):
            ToolRegistry._validate_endpoint("http://example.com/api")
        with self.assertRaises(ValueError):
            ToolRegistry._validate_endpoint("https://127.0.0.1/api")

    def test_rejects_invalid_method(self):
        with patch.object(ToolRegistry, "_validate_endpoint", side_effect=lambda value: value):
            with self.assertRaises(ValueError):
                self.registry.create({**self.payload, "method": "DELETE"})


class ToolManagerAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_handler_is_supported(self):
        manager = ToolManager()
        async def handler(args):
            return {"echo": args.get("value")}
        manager.register("async_test", "test", {"type": "object", "properties": {}}, handler)
        result = await manager.execute_async_result("async_test", {"value": "ok"})
        self.assertTrue(result["success"])
        self.assertEqual(result["result"]["echo"], "ok")


if __name__ == "__main__":
    unittest.main()
