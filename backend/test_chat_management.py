"""Focused tests for conversation/category deletion endpoints."""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from backend import main


class ChatManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self.chats_file = base / "chats.json"
        self.categories_file = base / "categories.json"
        self.chats_file.write_text(json.dumps([
            {"id": "keep-1", "title": "Keep me", "category": "Work", "messages": [{"role": "user", "content": "x"}]},
            {"id": "delete-1", "title": "Delete me", "category": "Learning", "messages": [{"role": "user", "content": "y"}]},
        ]), encoding="utf-8")
        self.categories_file.write_text(json.dumps(["Work", "Learning"]), encoding="utf-8")
        self.patchers = [
            patch.object(main, "CHATS_FILE", self.chats_file),
            patch.object(main, "CATEGORIES_FILE", self.categories_file),
        ]
        for item in self.patchers:
            item.start()

    def tearDown(self):
        for item in self.patchers:
            item.stop()
        self.temp_dir.cleanup()

    def test_delete_category_preserves_conversations_as_uncategorised(self):
        result = asyncio.run(main.delete_category("Learning"))
        chats = json.loads(self.chats_file.read_text(encoding="utf-8"))
        categories = json.loads(self.categories_file.read_text(encoding="utf-8"))
        self.assertEqual(result["moved_conversations"], 1)
        self.assertEqual(categories, ["Work"])
        self.assertEqual(next(chat for chat in chats if chat["id"] == "delete-1")["category"], "未分类")
        self.assertEqual(len(chats), 2)

    def test_delete_chat_removes_conversation_and_messages(self):
        result = asyncio.run(main.delete_chat("delete-1"))
        chats = json.loads(self.chats_file.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "deleted")
        self.assertEqual([chat["id"] for chat in chats], ["keep-1"])

    def test_delete_missing_chat_returns_404(self):
        with self.assertRaises(HTTPException) as context:
            asyncio.run(main.delete_chat("missing"))
        self.assertEqual(context.exception.status_code, 404)

    def test_protected_category_cannot_be_deleted(self):
        with self.assertRaises(HTTPException) as context:
            asyncio.run(main.delete_category("未分类"))
        self.assertEqual(context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
