from __future__ import annotations

import shutil
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


class WorkspaceFileManager:
    """Safe file operations confined to the configured AgentWorkspace root."""
    def __init__(self, root: Path, state_dir: Path, blocked_names: set[str] | None = None) -> None:
        self.root = root.resolve()
        self.state_dir = state_dir.resolve()
        self.blocked_names = blocked_names or {".git", ".venv", "venv", "node_modules", "__pycache__"}

    def resolve(self, relative: str, *, allow_root: bool = False) -> Path:
        if not isinstance(relative, str) or not relative.strip():
            raise ValueError("A workspace-relative path is required.")
        raw = Path(relative)
        if raw.is_absolute():
            raise ValueError("Absolute paths are not allowed.")
        # Inspect the lexical path before resolving it so symlinks cannot hide traversal.
        lexical = self.root / raw
        cursor = self.root
        for part in raw.parts:
            if part in {"", "."}:
                continue
            if part == "..":
                raise ValueError("Parent-directory traversal is not allowed.")
            cursor = cursor / part
            if cursor.is_symlink():
                raise PermissionError("Symbolic links are not accessible through Agent file tools.")
        target = lexical.resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError("Path is outside the authorised workspace.")
        if target == self.root and not allow_root:
            raise ValueError("This operation cannot target the workspace root itself.")
        if target == self.state_dir or self.state_dir in target.parents:
            raise PermissionError("Agent internal state is not accessible.")
        parts = target.relative_to(self.root).parts if target != self.root else ()
        if any(part.startswith(".") or part in self.blocked_names for part in parts):
            raise PermissionError("Hidden, secret and dependency paths are blocked.")
        return target

    def list(self, directory: str = ".") -> dict[str, Any]:
        folder = self.root if directory in {"", "."} else self.resolve(directory, allow_root=True)
        if not folder.is_dir():
            raise ValueError("Directory does not exist.")
        items = []
        for child in sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.casefold())):
            if child.name.startswith(".") or child.name in self.blocked_names:
                continue
            if child.is_symlink():
                continue
            items.append({"name": child.name, "path": child.relative_to(self.root).as_posix(), "kind": "directory" if child.is_dir() else "file", "size": child.stat().st_size if child.is_file() else None})
            if len(items) >= 300:
                break
        return {"directory": directory or ".", "items": items}

    def read(self, path: str) -> dict[str, Any]:
        target = self.resolve(path)
        if not target.is_file():
            raise ValueError("File does not exist.")
        if target.stat().st_size > 2_000_000:
            raise ValueError("File exceeds the 2 MB read limit.")
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("This file is not UTF-8 text. Binary/document parsing is not enabled yet.") from exc
        return {"path": path, "content": content}

    def write(self, path: str, content: str, *, overwrite: bool = False) -> dict[str, Any]:
        target = self.resolve(path)
        if target.suffix.lower() not in {".txt", ".md", ".py", ".json", ".csv", ".yaml", ".yml", ".toml", ".js", ".jsx", ".ts", ".tsx", ".css", ".html", ".sql"}:
            raise ValueError("Only supported text and source files can be written.")
        if len(content.encode("utf-8")) > 2_000_000:
            raise ValueError("File content exceeds the 2 MB write limit.")
        if target.exists() and not overwrite:
            raise FileExistsError("File already exists. Set overwrite=true only when replacement is intended.")
        if not target.parent.is_dir():
            raise ValueError("Parent directory does not exist.")
        backup = None
        if target.exists():
            backup_dir = self.state_dir / "file_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup = backup_dir / f"{target.name}.{stamp}.bak"
            shutil.copy2(target, backup)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, prefix=".agent-write-", suffix=".tmp", delete=False) as handle:
                handle.write(content)
                temporary = Path(handle.name)
            os.replace(temporary, target)
        except OSError:
            if temporary:
                temporary.unlink(missing_ok=True)
            raise
        return {"path": path, "created": backup is None, "backup_created": backup is not None}

    def create_directory(self, path: str) -> dict[str, Any]:
        target = self.resolve(path)
        target.mkdir(parents=False, exist_ok=False)
        return {"path": path, "created": True}

    def move(self, source: str, destination: str) -> dict[str, Any]:
        src = self.resolve(source)
        dst = self.resolve(destination, allow_root=True)
        if not src.exists() or not dst.is_dir():
            raise ValueError("Source must exist and destination must be an existing directory.")
        if src.is_dir() and (dst == src or src in dst.parents):
            raise ValueError("A directory cannot be moved into itself or a descendant.")
        target = dst / src.name
        if target.exists():
            raise FileExistsError("Destination already contains an item with this name.")
        shutil.move(str(src), str(target))
        return {"source": source, "destination": target.relative_to(self.root).as_posix()}

    def rename(self, path: str, new_name: str) -> dict[str, Any]:
        src = self.resolve(path)
        name = Path(new_name).name
        if not src.exists() or not name or name.startswith(".") or name in {".", ".."}:
            raise ValueError("Invalid source or new name.")
        target = src.with_name(name)
        if target.exists():
            raise FileExistsError("An item with the new name already exists.")
        src.rename(target)
        return {"old_path": path, "new_path": target.relative_to(self.root).as_posix()}

    def copy(self, source: str, destination: str) -> dict[str, Any]:
        src = self.resolve(source)
        dst = self.resolve(destination, allow_root=True)
        if not src.exists() or not dst.is_dir():
            raise ValueError("Source must exist and destination must be an existing directory.")
        target = dst / src.name
        if target.exists():
            raise FileExistsError("Destination already contains an item with this name.")
        if src.is_dir():
            shutil.copytree(src, target, symlinks=True, ignore=shutil.ignore_patterns(".*", *self.blocked_names))
        else:
            shutil.copy2(src, target)
        return {"source": source, "destination": target.relative_to(self.root).as_posix(), "copied": True}

    def delete(self, path: str) -> dict[str, Any]:
        target = self.resolve(path)
        if not target.exists():
            raise ValueError("Item does not exist.")
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return {"path": path, "deleted": True}


def register_file_tools(manager: Any, file_manager: WorkspaceFileManager, *, allow_write: bool, allow_read: bool = True, allow_delete: bool = True) -> None:
    if allow_read:
        manager.register("workspace_list", "List files and directories within the user-authorised workspace. Hidden, secret and internal state paths are excluded.", {"type":"object","properties":{"directory":{"type":"string"}},"required":["directory"],"additionalProperties":False}, lambda a: file_manager.list(a["directory"]))
        manager.register("workspace_read", "Read a UTF-8 text or source file within the user-authorised workspace.", {"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}, lambda a: file_manager.read(a["path"]))
    if allow_write:
        manager.register("workspace_write", "Create or overwrite a supported text/source file inside the authorised workspace. Existing files are backed up before replacement.", {"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"},"overwrite":{"type":"boolean"}},"required":["path","content"],"additionalProperties":False}, lambda a: file_manager.write(a["path"], a["content"], overwrite=bool(a.get("overwrite", False))))
        manager.register("workspace_create_directory", "Create one directory inside the authorised workspace. Parent directory must already exist.", {"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}, lambda a: file_manager.create_directory(a["path"]))
        manager.register("workspace_move", "Move a file or directory into an existing authorised workspace directory.", {"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"}},"required":["source","destination"],"additionalProperties":False}, lambda a: file_manager.move(a["source"], a["destination"]))
        manager.register("workspace_rename", "Rename a file or directory inside the authorised workspace.", {"type":"object","properties":{"path":{"type":"string"},"new_name":{"type":"string"}},"required":["path","new_name"],"additionalProperties":False}, lambda a: file_manager.rename(a["path"], a["new_name"]))
        manager.register("workspace_copy", "Copy a file or directory into an existing authorised workspace directory.", {"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"}},"required":["source","destination"],"additionalProperties":False}, lambda a: file_manager.copy(a["source"], a["destination"]))
    if allow_write and allow_delete:
        manager.register("workspace_delete", "Delete a file or directory inside the authorised workspace. Only use when the user explicitly requests deletion.", {"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}, lambda a: file_manager.delete(a["path"]))
