from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.tools import sqlite_operations
from backend.tools.file_management_tools import WorkspaceFileManager
from backend import main


class SQLitePermissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "test.db"
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
            conn.execute("INSERT INTO sample(value) VALUES ('one')")
        self.patch = patch.object(sqlite_operations, "DB_PATH", self.db)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_query_returns_rows(self):
        result = sqlite_operations.query_sql({"sql": "SELECT id, value FROM sample"})
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["rows"][0]["value"], "one")

    def test_query_cannot_modify(self):
        with self.assertRaises(sqlite3.DatabaseError):
            sqlite_operations.query_sql({"sql": "DELETE FROM sample"})
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sample").fetchone()[0], 1)

    def test_modify_can_insert(self):
        result = sqlite_operations.modify_sql({"sql": "INSERT INTO sample(value) VALUES ('two')"})
        self.assertEqual(result["affected_rows"], 1)

    def test_modify_cannot_attach_database(self):
        with self.assertRaises(sqlite3.DatabaseError):
            sqlite_operations.modify_sql({"sql": "ATTACH DATABASE ':memory:' AS other"})


class WorkspaceFileManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "workspace"
        self.state = self.root / ".agent_state"
        self.root.mkdir()
        self.state.mkdir()
        (self.root / "docs").mkdir()
        self.manager = WorkspaceFileManager(self.root, self.state)

    def tearDown(self):
        self.temp.cleanup()

    def test_read_and_write_confined_files(self):
        (self.root / "docs" / "a.txt").write_text("hello", encoding="utf-8")
        self.assertEqual(self.manager.read("docs/a.txt")["content"], "hello")
        self.manager.write("docs/b.txt", "world")
        self.assertEqual((self.root / "docs" / "b.txt").read_text(), "world")

    def test_blocks_parent_traversal_and_internal_state(self):
        with self.assertRaises(ValueError):
            self.manager.resolve("../outside.txt")
        with self.assertRaises(PermissionError):
            self.manager.resolve(".agent_state/chats.json")

    def test_blocks_symlinks(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.root / "linked").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(PermissionError):
            self.manager.resolve("linked/secret.txt")


class WorkspaceApiPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "workspace"
        self.root.mkdir()
        self.state = self.root / ".agent_state"
        self.state.mkdir()
        self.patchers = [patch.object(main, "WORKSPACE", self.root), patch.object(main, "STATE_DIR", self.state)]
        for item in self.patchers:
            item.start()

    def tearDown(self):
        for item in self.patchers:
            item.stop()
        self.temp.cleanup()

    def test_workspace_api_blocks_hidden_and_parent_paths(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            main._workspace_path(".env")
        with self.assertRaises(HTTPException):
            main._workspace_path("../outside")

    def test_workspace_api_blocks_symlinks(self):
        from fastapi import HTTPException
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.root / "link").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(HTTPException):
            main._workspace_path("link/secret.txt")


if __name__ == "__main__":
    unittest.main()
