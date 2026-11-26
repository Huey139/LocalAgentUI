from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


logger = logging.getLogger("local_agent")


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from .database import initialize_database, connect
from .version import APP_VERSION
from .team_orchestration_api import router as team_orchestration_router, analyze_proposal_team_plan
from .workspace_api import router as workspace_management_router, register_workspace_tools, register_business_context_tool
from .project_api import (
    router as project_management_router,
    TaskCreate, TaskUpdate, AssignmentCreate, DependencyCreate,
    list_projects, list_agents, list_project_tasks, get_project, create_task, update_task, assign_task, add_task_dependency,
    authorize_project_execution, is_project_execution_authorized,
)
from .proposal_api import (
    router as proposal_management_router, ProposalCreate, ProposalUpdate, ProposalDecision, LifecycleComment,
    create_proposal, update_proposal, get_proposal, decide_proposal, resubmit_proposal, authorize_planning, formally_approve_proposal,
)
from .tools.tool_manager import ToolManager
from .intent_router import classify_intent
from .tools.database_tools import register_database_tools
from .tools.sqlite_operations import register_sqlite_operation_tools
from .tools.file_management_tools import WorkspaceFileManager, register_file_tools
from .capability_catalog import get_assignable_capability_ids, list_system_capabilities, resolve_agent_tool_permissions
from .tools.tool_registry import ToolRegistry
from .prompts.prompt_manager import assemble_main_agent_prompt
from .context.context_manager import build_session_context
from .context.runtime_environment import build_runtime_environment
from .project_prompts import initialise_project_prompt, get_project_prompt, update_project_prompt
from .agents import AgentRegistry, AgentRuntime, AgentDispatcher

WORKSPACE = Path(
    os.getenv("AGENT_WORKSPACE", str(Path.home() / "AgentWorkspace"))
).expanduser().resolve()
STATE_DIR = WORKSPACE / ".agent_state"
CHATS_FILE = STATE_DIR / "chats.json"
CATEGORIES_FILE = STATE_DIR / "categories.json"
PROJECT_SETTINGS_FILE = STATE_DIR / "project_permissions.json"
SPECIALIST_AGENTS_FILE = STATE_DIR / "specialist_agents.json"
MAIN_AGENT_CONFIG_FILE = STATE_DIR / "main_agent_config.json"
TOOL_REGISTRY_FILE = STATE_DIR / "tools.json"
DEFAULT_CATEGORIES = ["Work", "Learning", "Ideas"]
WORKSPACE.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "")
TEXT_EXTENSIONS = {".txt", ".md", ".py", ".json", ".csv", ".yaml", ".yml", ".toml"}
MAX_CONTEXT_CHARS_PER_FILE = 12000
MAX_PROJECT_FILE_BYTES = 40_000
MAX_PROJECT_WRITE_BYTES = 80_000
BLOCKED_PROJECT_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".agent_backups"}
PROJECT_TEXT_EXTENSIONS = {".md", ".txt", ".py", ".jsx", ".js", ".tsx", ".ts", ".css", ".html", ".json", ".toml", ".yaml", ".yml"}

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Database bootstrap and validation must finish before the API accepts traffic.
    # Any migration or validation error intentionally aborts application startup.
    initialize_database()
    yield


app = FastAPI(title="Local Agent", lifespan=lifespan)
app.include_router(project_management_router)
app.include_router(team_orchestration_router)
app.include_router(proposal_management_router)
app.include_router(workspace_management_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class NewChat(BaseModel):
    category: str = "Uncategorised"
    project_id: str | None = None


class NewCategory(BaseModel):
    name: str


class RenameCategory(BaseModel):
    old_name: str
    new_name: str


class ChatUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    project_id: str | None = None


class SendMessage(BaseModel):
    content: str
    context_files: list[str] = []
    model: str | None = None


class ChatActionRequest(BaseModel):
    action: str
    proposal_id: str
    snapshot_hash: str | None = None


class ProjectSettingsUpdate(BaseModel):
    project_root: str | None = None
    read_enabled: bool | None = None
    write_enabled: bool | None = None


class NewFolder(BaseModel):
    path: str


class MoveFile(BaseModel):
    source: str
    destination_folder: str


class RenameFile(BaseModel):
    source: str
    new_name: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_chats() -> list[dict[str, Any]]:
    if not CHATS_FILE.exists():
        return []
    try:
        data = json.loads(CHATS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write_chats(chats: list[dict[str, Any]]) -> None:
    temp_file = CHATS_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(chats, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(CHATS_FILE)


def _read_categories() -> list[str]:
    if not CATEGORIES_FILE.exists():
        return DEFAULT_CATEGORIES.copy()
    try:
        data = json.loads(CATEGORIES_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list) and all(isinstance(item, str) for item in data):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return DEFAULT_CATEGORIES.copy()


def _write_categories(categories: list[str]) -> None:
    temp_file = CATEGORIES_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(categories, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(CATEGORIES_FILE)


def _project_settings() -> dict[str, Any]:
    defaults = {"project_root": str(PROJECT_ROOT), "read_enabled": True, "write_enabled": True}
    try:
        saved = json.loads(PROJECT_SETTINGS_FILE.read_text(encoding="utf-8"))
        root = Path(saved.get("project_root", defaults["project_root"])).expanduser().resolve()
        if not root.is_dir():
            root = PROJECT_ROOT
        read_enabled = bool(saved.get("read_enabled", defaults["read_enabled"]))
        write_enabled = bool(saved.get("write_enabled", defaults["write_enabled"])) and read_enabled
        return {"project_root": str(root), "read_enabled": read_enabled, "write_enabled": write_enabled}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return defaults


def _save_project_settings(settings: dict[str, Any]) -> None:
    temp_file = PROJECT_SETTINGS_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(PROJECT_SETTINGS_FILE)


def _project_path(relative_path: str) -> Path:
    settings = _project_settings()
    if not settings["read_enabled"]:
        raise HTTPException(status_code=403, detail="Project file access is disabled. Enable it in Project Permissions.")
    root = Path(settings["project_root"]).resolve()
    raw = Path(relative_path or "")
    if not relative_path or raw.is_absolute() or ".." in raw.parts:
        raise HTTPException(status_code=400, detail="Provide a safe relative path within the selected project directory.")
    lexical = root / raw
    cursor = root
    for part in raw.parts:
        if part in {"", "."}:
            continue
        cursor = cursor / part
        if cursor.is_symlink():
            raise HTTPException(status_code=403, detail="Symbolic links are not accessible through project file tools.")
    candidate = lexical.resolve()
    if candidate == root or root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Only files within the currently selected project directory can be accessed.")
    relative_parts = candidate.relative_to(root).parts
    if any(part in BLOCKED_PROJECT_DIRS or part.startswith(".") for part in relative_parts):
        raise HTTPException(status_code=403, detail="Hidden files, secret files, and dependency directories are not accessible to the Agent.")
    return candidate


def _project_file(relative_path: str, *, for_write: bool = False) -> Path:
    settings = _project_settings()
    if for_write and not settings["write_enabled"]:
        raise HTTPException(status_code=403, detail="Project write access is disabled. Enable it in Project Permissions.")
    candidate = _project_path(relative_path)
    if candidate.suffix.lower() not in PROJECT_TEXT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only common text and source-code files are supported.")
    return candidate


def _list_project_files(directory: str = ".") -> str:
    settings = _project_settings()
    root = Path(settings["project_root"]).resolve()
    if directory in ("", "."):
        folder = root
    else:
        folder = _project_path(directory)
    if not folder.is_dir():
        return f"Not a project directory: {directory}"
    rows = []
    try:
        for item in sorted(folder.iterdir(), key=lambda path: (path.is_file(), path.name.casefold())):
            if item.is_symlink() or item.name.startswith(".") or item.name in BLOCKED_PROJECT_DIRS:
                continue
            if item.is_dir():
                rows.append(f"Directory: {item.relative_to(root).as_posix()}/")
            elif item.suffix.lower() in PROJECT_TEXT_EXTENSIONS:
                rows.append(f"File: {item.relative_to(root).as_posix()}")
            if len(rows) >= 120:
                rows.append("(Listing truncated)")
                break
    except OSError as exc:
        return f"Failed to read directory: {exc}"
    return "\n".join(rows) or "No displayable source-code or text files were found in this directory."


def _read_project_file(relative_path: str) -> str:
    path = _project_file(relative_path)
    if not path.is_file():
        return f"File not found: {relative_path}"
    if path.stat().st_size > MAX_PROJECT_FILE_BYTES:
        return f"File exceeds {MAX_PROJECT_FILE_BYTES // 1000} KB and cannot be read: {relative_path}"
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return f"Failed to read file: {exc}"


def _write_project_file(relative_path: str, content: str) -> str:
    path = _project_file(relative_path, for_write=True)
    if len(content.encode("utf-8")) > MAX_PROJECT_WRITE_BYTES:
        return f"File content exceeds {MAX_PROJECT_WRITE_BYTES // 1000} KB. Write operation rejected."
    root = Path(_project_settings()["project_root"]).resolve()
    if not path.parent.is_dir():
        return "The destination folder does not exist. Select an existing folder in the project."
    backups = STATE_DIR / "project_file_backups"
    backup_path = None
    if path.exists():
        relative = path.relative_to(root)
        backup_path = backups / relative
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_path = backup_path.with_name(f"{backup_path.name}.{stamp}.bak")
        shutil.copy2(path, backup_path)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".agent-", suffix=".tmp", delete=False) as handle:
            handle.write(content)
            temporary_path = Path(handle.name)
        os.replace(temporary_path, path)
    except OSError as exc:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        return f"Write failed: {exc}"
    root_label = path.relative_to(root).as_posix()
    backup_label = f"(Original file backup: {backup_path})" if backup_path else "(New file)"
    return f"Project file written: {root_label} {backup_label}"


def _replace_project_text(relative_path: str, old_text: str, new_text: str) -> str:
    path = _project_file(relative_path, for_write=True)
    if not path.is_file():
        return f"File not found: {relative_path}"
    if path.stat().st_size > MAX_PROJECT_FILE_BYTES:
        return f"File exceeds {MAX_PROJECT_FILE_BYTES // 1000} KB and cannot be modified: {relative_path}"
    try:
        original = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return f"Failed to read file: {exc}"
    occurrences = original.count(old_text) if old_text else 0
    if occurrences == 0:
        return "The original text was not found. Read the file again and provide an exact match."
    if occurrences > 1:
        return f"The original text occurs {occurrences} times, so the target is ambiguous. Provide a longer, unique text fragment."
    return _write_project_file(relative_path, original.replace(old_text, new_text, 1))


def _get_chat(chat_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    chats = _read_chats()
    for chat in chats:
        if chat["id"] == chat_id:
            return chats, chat
    raise HTTPException(status_code=404, detail="Conversation not found.")


def _workspace_path(relative_path: str) -> Path:
    raw = Path(relative_path or ".")
    if raw.is_absolute() or ".." in raw.parts:
        raise HTTPException(status_code=400, detail="Only safe relative paths within AgentWorkspace can be accessed.")
    cursor = WORKSPACE
    for part in raw.parts:
        if part in {"", "."}:
            continue
        if part.startswith(".") or part in BLOCKED_PROJECT_DIRS:
            raise HTTPException(status_code=403, detail="Hidden, internal and dependency paths are not accessible.")
        cursor = cursor / part
        if cursor.is_symlink():
            raise HTTPException(status_code=403, detail="Symbolic links are not accessible through Workspace.")
    candidate = cursor.resolve()
    if candidate != WORKSPACE and WORKSPACE not in candidate.parents:
        raise HTTPException(status_code=400, detail="Only files within AgentWorkspace can be accessed.")
    if candidate == STATE_DIR or STATE_DIR in candidate.parents:
        raise HTTPException(status_code=400, detail="The Agent internal state directory cannot be accessed.")
    return candidate


def _unique_path(directory: Path, filename: str) -> Path:
    desired = directory / Path(filename).name
    if not desired.exists():
        return desired
    stem, suffix = desired.stem, desired.suffix
    number = 2
    while True:
        candidate = directory / f"{stem} ({number}){suffix}"
        if not candidate.exists():
            return candidate
        number += 1


def _tree(folder: Path) -> list[dict[str, Any]]:
    result = []
    try:
        children = sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.casefold()))
    except OSError:
        return result
    for item in children:
        if item.is_symlink() or item == STATE_DIR or STATE_DIR in item.parents or item.name.startswith("."):
            continue
        relative = item.relative_to(WORKSPACE).as_posix()
        entry: dict[str, Any] = {
            "name": item.name,
            "path": relative,
            "kind": "folder" if item.is_dir() else "file",
        }
        if item.is_dir():
            entry["children"] = _tree(item)
        else:
            entry["size"] = item.stat().st_size
            entry["extension"] = item.suffix.lower()
        result.append(entry)
    return result


async def _search_web(query: str) -> str:
    if not SERPAPI_API_KEY:
        return "Web search is not configured because SERPAPI_API_KEY is missing. Add the key to the .env file in the project root and restart the app."
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://serpapi.com/search.json",
                params={"engine": "google", "q": query, "api_key": SERPAPI_API_KEY, "hl": "en", "gl": "nz"},
            )
            response.raise_for_status()
            payload = response.json()
        results = payload.get("organic_results", [])[:5]
        if not results:
            return "No relevant search results were found."
        return "\n\n".join(
            f"{index}. {item.get('title', 'Search result')}\n{item.get('snippet', '')}\n{item.get('link', '')}"
            for index, item in enumerate(results, start=1)
        )
    except Exception as exc:
        logger.exception("Web search failed. error_type=%s error=%s", type(exc).__name__, str(exc))
        return f"Web search is temporarily unavailable: {exc}"


@app.get("/api/capabilities")
async def get_system_capabilities() -> dict[str, Any]:
    return {"capabilities": list_system_capabilities()}


@app.get("/api/status")
async def status() -> dict[str, str]:
    return {"version": APP_VERSION, "model": OLLAMA_MODEL, "workspace": str(WORKSPACE), "search_ready": str(bool(SERPAPI_API_KEY)).lower()}


def _main_agent_config() -> dict[str, Any]:
    try:
        config = json.loads(MAIN_AGENT_CONFIG_FILE.read_text(encoding="utf-8"))
        if isinstance(config, dict):
            return {"model": str(config.get("model") or OLLAMA_MODEL)}
    except (OSError, json.JSONDecodeError):
        pass
    return {"model": OLLAMA_MODEL}


def _validate_agent_tool_permissions(items: list[dict[str, Any]]) -> None:
    known_tools = {item["function_name"] for item in ToolRegistry(TOOL_REGISTRY_FILE).list_tools()} | {"sqlite_modify", "workspace_modify"}
    for item in items:
        requested_tools = item.get("allowed_tools", [])
        denied_tools = item.get("denied_tools", [])
        requested_capabilities = item.get("capabilities", [])
        if not isinstance(requested_tools, list) or any(tool_name not in known_tools for tool_name in requested_tools):
            raise ValueError("Agent Direct Tool Permissions contain an unknown Tool. Refresh Tool Management and try again.")
        if not isinstance(denied_tools, list) or any(tool_name not in known_tools | {"sqlite_query", "workspace_list", "workspace_read", "workspace_write", "workspace_create_directory", "workspace_move", "workspace_rename", "workspace_copy"} for tool_name in denied_tools):
            raise ValueError("Agent Denied Tools contain an unknown Tool.")
        if not isinstance(requested_capabilities, list):
            raise ValueError("Agent Capabilities must be a list of Capability IDs.")
        # Unknown legacy labels remain descriptive-only for backward compatibility;
        # only registered, assignable IDs can grant runtime tools.


@app.get("/api/agents")
async def get_specialist_agents() -> dict[str, Any]:
    registry = AgentRegistry(config_path=SPECIALIST_AGENTS_FILE)
    return {"main_agent": _main_agent_config(), "agents": registry.list_agents(include_prompt=True)}


class SpecialistAgentConfiguration(BaseModel):
    agents: list[dict[str, Any]]


class MainAgentConfiguration(BaseModel):
    model: str


@app.put("/api/agents/main")
async def update_main_agent_configuration(payload: MainAgentConfiguration) -> dict[str, Any]:
    model = payload.model.strip()
    if not model or len(model) > 160:
        raise HTTPException(status_code=400, detail="Select a valid installed model for Main Agent.")
    MAIN_AGENT_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = MAIN_AGENT_CONFIG_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps({"model": model}, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        temp.chmod(0o600)
    except OSError:
        pass
    temp.replace(MAIN_AGENT_CONFIG_FILE)
    return {"success": True, "main_agent": {"model": model}}


@app.post("/api/agents")
async def create_specialist_agent(payload: dict[str, Any]) -> dict[str, Any]:
    registry = AgentRegistry(config_path=SPECIALIST_AGENTS_FILE)
    try:
        _validate_agent_tool_permissions([payload])
        agent = registry.create_custom(payload)
        return {"success": True, "agent": agent}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/agents")
async def update_specialist_agents(payload: SpecialistAgentConfiguration) -> dict[str, Any]:
    registry = AgentRegistry(config_path=SPECIALIST_AGENTS_FILE)
    try:
        _validate_agent_tool_permissions(payload.agents)
        agents = registry.save_configuration(payload.agents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "agents": agents}


@app.put("/api/agents/{agent_id}")
async def update_custom_specialist_agent(agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    registry = AgentRegistry(config_path=SPECIALIST_AGENTS_FILE)
    try:
        _validate_agent_tool_permissions([payload])
        existing = next((item for item in registry.list_agents() if item["agent_id"] == agent_id), None)
        if existing is None:
            raise KeyError("Agent not found.")
        if existing.get("is_custom"):
            agent = registry.update_custom(agent_id, payload)
        else:
            payload = {**payload, "agent_id": agent_id}
            agents = registry.save_configuration([payload])
            agent = next(item for item in agents if item["agent_id"] == agent_id)
            agent["role_prompt"] = registry.get(agent_id).role_prompt if registry.get(agent_id) else ""
        return {"success": True, "agent": agent}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/agents/{agent_id}")
async def delete_custom_specialist_agent(agent_id: str) -> dict[str, Any]:
    registry = AgentRegistry(config_path=SPECIALIST_AGENTS_FILE)
    try:
        registry.delete_custom(agent_id)
        return {"success": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class ToolDefinitionPayload(BaseModel):
    name: str
    description: str
    category: str = "other"
    endpoint: str
    method: str = "GET"
    function_name: str | None = None
    parameters: dict[str, Any] = {}
    required: list[str] = []
    credential_env: str = ""


@app.get("/api/tools")
async def get_configured_tools() -> dict[str, Any]:
    return {"tools": ToolRegistry(TOOL_REGISTRY_FILE).list_tools()}


@app.post("/api/tools")
async def create_configured_tool(payload: ToolDefinitionPayload) -> dict[str, Any]:
    try:
        item = ToolRegistry(TOOL_REGISTRY_FILE).create(payload.model_dump())
        return {"success": True, "tool": item}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/tools/{tool_id}")
async def update_configured_tool(tool_id: str, payload: ToolDefinitionPayload) -> dict[str, Any]:
    try:
        item = ToolRegistry(TOOL_REGISTRY_FILE).update(tool_id, payload.model_dump())
        return {"success": True, "tool": item}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ToolStatusPayload(BaseModel):
    enabled: bool


@app.patch("/api/tools/{tool_id}/status")
async def set_configured_tool_status(tool_id: str, payload: ToolStatusPayload) -> dict[str, Any]:
    try:
        return {"success": True, "tool": ToolRegistry(TOOL_REGISTRY_FILE).set_enabled(tool_id, payload.enabled)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/tools/{tool_id}")
async def delete_configured_tool(tool_id: str) -> dict[str, Any]:
    try:
        for agent in AgentRegistry(config_path=SPECIALIST_AGENTS_FILE).list_agents():
            if tool_id in agent.get("allowed_tools", []):
                raise HTTPException(status_code=409, detail=f"Tool is assigned to {agent['display_name']}. Remove the permission before deleting it.")
        registry = ToolRegistry(TOOL_REGISTRY_FILE)
        item = registry.get(tool_id)
        if item and any(tool_id in agent.get("allowed_tools", []) or item.get("function_name") in agent.get("allowed_tools", []) for agent in AgentRegistry(config_path=SPECIALIST_AGENTS_FILE).list_agents()):
            raise HTTPException(status_code=409, detail="Tool is assigned to an Agent. Remove the permission before deleting it.")
        registry.delete(tool_id)
        return {"success": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/models")
async def list_models() -> dict[str, Any]:
    """List models currently installed in the local Ollama instance."""
    ollama_root = OLLAMA_BASE_URL.removesuffix("/v1")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{ollama_root}/api/tags")
            response.raise_for_status()
        models = [item["name"] for item in response.json().get("models", []) if item.get("name")]
        return {"models": models, "default": OLLAMA_MODEL}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to retrieve the Ollama model list: {exc}") from exc


@app.get("/api/project")
async def get_project_settings() -> dict[str, Any]:
    return _project_settings()


@app.patch("/api/project")
async def update_project_settings(payload: ProjectSettingsUpdate) -> dict[str, Any]:
    settings = _project_settings()
    if payload.project_root is not None:
        root = Path(payload.project_root).expanduser().resolve()
        if not root.is_dir():
            raise HTTPException(status_code=400, detail="The project directory does not exist or is not a folder.")
        settings["project_root"] = str(root)
    if payload.read_enabled is not None:
        settings["read_enabled"] = payload.read_enabled
        if not payload.read_enabled:
            settings["write_enabled"] = False
    if payload.write_enabled is not None:
        if payload.write_enabled and not settings["read_enabled"]:
            raise HTTPException(status_code=400, detail="Enable project file read access before enabling write access.")
        settings["write_enabled"] = payload.write_enabled
    _save_project_settings(settings)
    return settings


def _project_tool_schemas(settings: dict[str, Any]) -> list[dict[str, Any]]:
    tools = []
    if settings["read_enabled"]:
        tools.extend([
            {
                "type": "function",
                "function": {
                    "name": "list_project_files",
                    "description": "List source-code and text files in the current project. Use paths relative to the project root; use a period (.) for the root directory.",
                    "parameters": {"type": "object", "properties": {"directory": {"type": "string", "description": "A directory path relative to the project root, such as frontend/src. Use . for the root directory."}}, "required": ["directory"]},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_project_file",
                    "description": "Read a source-code or text file from the current project. Only project-relative paths are allowed.",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "A file path relative to the project root, such as frontend/src/App.jsx."}}, "required": ["path"]},
                },
            },
        ])
    if settings["write_enabled"]:
        tools.extend([
            {
                "type": "function",
                "function": {
                    "name": "replace_project_text",
                    "description": "Make a small edit by replacing a unique text fragment. Read the file first. The original fragment must match exactly once; a backup is created automatically.",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "A file path relative to the project root."}, "old_text": {"type": "string", "description": "Text copied exactly from the file and occurring only once."}, "new_text": {"type": "string", "description": "The replacement text."}}, "required": ["path", "old_text", "new_text"]},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_project_file",
                    "description": "Create or fully rewrite a source-code or text file in the current project when explicitly requested by the user. Read the existing file first. Do not modify hidden files, secrets, dependencies, or files outside the project root.",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "A file path relative to the project root."}, "content": {"type": "string", "description": "The complete file content to write."}}, "required": ["path", "content"]},
                },
            },
        ])
    return tools


def _execute_project_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "list_project_files":
        return {"directory": str(arguments.get("directory", ".")),
                "content": _list_project_files(str(arguments.get("directory", ".")))}
    if name == "read_project_file":
        path = str(arguments.get("path", ""))
        return {"path": path, "content": _read_project_file(path)}
    if name == "write_project_file":
        path = str(arguments.get("path", ""))
        message = _write_project_file(path, str(arguments.get("content", "")))
        return {"path": path, "message": message, "written": message.startswith("Project file written:")}
    if name == "replace_project_text":
        path = str(arguments.get("path", ""))
        message = _replace_project_text(path, str(arguments.get("old_text", "")),
                                        str(arguments.get("new_text", "")))
        return {"path": path, "message": message,
                "updated": message.startswith("Project file written:")}
    raise ValueError(f"No tool named '{name}' is available.")



def _needs_management_mutations(user_text: str) -> bool:
    text = (user_text or "").lower()
    return bool(re.search(r"\b(create|add|assign|update|delete|remove|change)\b.{0,50}\b(project|task|agent|specialist)\b|\b(project|task|agent|specialist)\b.{0,50}\b(create|add|assign|update|delete|remove|change)\b|创建|新增|分配|更新|修改|删除.{0,10}(项目|任务|Agent)", text))


def _needs_management_tools(user_text: str) -> bool:
    import re
    text = user_text.lower()
    return bool(re.search(r"\b(list|show|find|create|add|assign|update|check)\b.{0,50}\b(projects?|tasks?|agents?|specialists?)\b|\b(projects?|tasks?|agents?|specialists?)\b.{0,50}\b(list|show|create|add|assign|update|check)\b", text))


def _management_tool_schemas(*, include_mutations: bool = True) -> list[dict[str, Any]]:
    def fn(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
        return {"type": "function", "function": {"name": name, "description": description, "parameters": {"type": "object", "properties": properties, "required": required or []}}}
    read_tools = [
        fn("list_projects", "Read-only: list formal projects available to the current workspace.", {}),
        fn("list_available_agents", "Read-only: list registered Agents and their roles and availability.", {}),
        fn("list_project_tasks", "Read-only: list tasks belonging to a formal project.", {"project_id": {"type": "string"}}, ["project_id"]),
    ]
    if not include_mutations:
        return read_tools
    return read_tools + [
        fn("create_project_task", "Main Agent only: create a task under an existing formal project.", {
            "project_id": {"type": "string"}, "name": {"type": "string"}, "description": {"type": "string"},
            "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
            "estimated_duration_minutes": {"type": "integer"}, "completion_criteria": {"type": "string"}
        }, ["project_id", "name", "completion_criteria"]),
        fn("assign_task_agent", "Main Agent only: assign an existing task to an enabled Agent.", {
            "task_id": {"type": "string"}, "agent_name": {"type": "string"}
        }, ["task_id", "agent_name"]),
        fn("update_project_task", "Main Agent only: update an existing task status, priority, or output summary.", {
            "task_id": {"type": "string"}, "status": {"type": "string", "enum": ["not_started", "in_progress", "blocked", "under_review", "rework_required", "completed", "cancelled"]},
            "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]}, "output_summary": {"type": "string"}
        }, ["task_id"]),
        fn("add_task_dependency", "Main Agent only: add a finish-to-start dependency between tasks in the same project.", {
            "task_id": {"type": "string"}, "depends_on_task_id": {"type": "string"}
        }, ["task_id", "depends_on_task_id"]),
    ]


def _as_plain_data(value: Any) -> Any:
    """Convert API/Pydantic objects into JSON-compatible Python data."""
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return value.model_dump(mode="json")
    if hasattr(value, "dict") and callable(value.dict):
        return value.dict()
    if isinstance(value, list):
        return [_as_plain_data(item) for item in value]
    if isinstance(value, tuple):
        return [_as_plain_data(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _as_plain_data(item) for key, item in value.items()}
    return value


def _execute_management_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "list_projects":
        result = list_projects()
    elif name == "list_available_agents":
        result = list_agents()
    elif name == "list_project_tasks":
        result = list_project_tasks(str(arguments.get("project_id", "")))
    elif name == "create_project_task":
        result = create_task(TaskCreate.model_validate(arguments))
    elif name == "update_project_task":
        values = dict(arguments)
        task_id = str(values.pop("task_id", ""))
        result = update_task(task_id, TaskUpdate.model_validate(values))
    elif name == "add_task_dependency":
        task_id = str(arguments.get("task_id", ""))
        result = add_task_dependency(
            task_id,
            DependencyCreate(depends_on_task_id=str(arguments.get("depends_on_task_id", ""))),
        )
    elif name == "assign_task_agent":
        candidates = list_agents()
        requested = str(arguments.get("agent_name", "")).casefold()
        agent = next((a for a in candidates
                      if a["name"].casefold() == requested or a["role"].casefold() == requested), None)
        if not agent:
            raise ValueError("Agent not found. Use list_available_agents first.")
        result = assign_task(str(arguments.get("task_id", "")), AssignmentCreate(agent_id=agent["id"]))
    else:
        raise ValueError(f"Unknown management tool: {name}")
    plain_result = _as_plain_data(result)
    if isinstance(plain_result, dict):
        return plain_result
    if isinstance(plain_result, list):
        return {"items": plain_result}
    return {"value": plain_result}



def _needs_search_tools(user_text: str) -> bool:
    text = (user_text or "").lower()
    return bool(re.search(r"\b(web search|search the web|internet search|online search|latest news|current news|latest information|latest developments|google search|search online|find online)\b|\b(search|look up)\b.{0,40}\b(news|latest|current|online|internet|documentation|release)\b|联网搜索|网上搜索|网络搜索|最新新闻|最新信息", text))


def _needs_database_modify(user_text: str) -> bool:
    text = (user_text or "").lower()
    return bool(re.search(r"\b(insert\s+into\b|update\s+[a-z_][a-z0-9_]*\s+set\b|delete\s+from\b|create\s+table\b|alter\s+table\b|drop\s+table\b|modify database|change database)|\b(add|insert|update|delete|modify|create|drop|alter)\b.{0,35}\b(database|table|record|row|data)\b|新增数据|插入数据|修改数据|删除数据|修改表|创建表|删除表", text))


def _needs_database_tools(user_text: str) -> bool:
    """Detect requests that need database schema metadata."""
    text = user_text.strip().lower()
    patterns = (
        r"\b(schema|table schema|table definition|table names|list tables|all tables|column|columns|foreign key|primary key|relationship|relationships|constraint|constraints|index|indexes|ddl|create table|create view|sqlite_master|insert into|delete from)\b|\bselect\b.{1,120}\bfrom\b|\bupdate\s+[a-z_][a-z0-9_]*\s+set\b|\b(query|show|list|retrieve)\b.{0,30}\b(database|table|records|rows)\b",
        r"\b(unique|check constraint|default constraint)\b",
        r"(数据表|表结构|字段|列名|主键|外键|表关系|数据关系|数据库结构|约束|索引|建表语句|默认值|有哪些表|表名|查询记录|查询数据|新增数据|插入数据|修改数据|删除数据)",
    )
    return bool(text) and any(re.search(pattern, text) for pattern in patterns)


def _database_tool_plan(
    user_text: str,
    available_tables: list[str],
) -> list[tuple[str, dict[str, Any]]]:
    """Select required read-only schema tools using backend-side rules."""
    text = user_text.casefold()
    table_names = [
        name for name in available_tables
        if isinstance(name, str) and name.strip()
    ]
    mentioned_tables = [
        name for name in table_names
        if re.search(
            rf"(?<![a-zA-Z0-9_]){re.escape(name.casefold())}(?![a-zA-Z0-9_])",
            text,
        )
    ]

    wants_relationships = any(term in text for term in (
        "foreign key", "foreign keys", "relationship", "relationships",
        "外键", "表关系", "数据关系",
    ))
    wants_definition = any(term in text for term in (
        "create table", "create view", "create sql", "ddl",
        "constraint", "constraints", "完整定义", "完整sql",
        "建表语句", "约束", "默认值", "unique", "check",
    ))
    wants_columns = any(term in text for term in (
        "column", "columns", "field", "fields", "schema",
        "structure", "字段", "列", "结构", "类型",
    ))
    wants_table_list = any(term in text for term in (
        "list tables", "all tables", "table names", "所有表",
        "全部表", "有哪些表", "表名",
    ))

    plan: list[tuple[str, dict[str, Any]]] = []
    if wants_relationships:
        plan.append(("get_table_relationships", {}))

    if mentioned_tables:
        for table_name in mentioned_tables:
            if wants_definition:
                plan.append(("get_table_definition", {"table_name": table_name}))
            if wants_columns or not wants_definition:
                plan.append(("get_table_schema", {"table_name": table_name}))
    elif wants_table_list or not (wants_relationships or wants_definition):
        plan.append(("list_database_tables", {}))

    unique_plan: list[tuple[str, dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    for name, arguments in plan:
        key = (name, json.dumps(arguments, sort_keys=True))
        if key not in seen:
            seen.add(key)
            unique_plan.append((name, arguments))
    return unique_plan


def _execute_database_preflight(
    tool_manager: ToolManager,
    user_text: str,
) -> tuple[list[dict[str, Any]], bool]:
    """Execute database metadata tools before asking the model to answer."""
    evidence: list[dict[str, Any]] = []
    try:
        inventory_raw = tool_manager.execute("list_database_tables", {})
        inventory = json.loads(inventory_raw)
        if not isinstance(inventory, dict) or not inventory.get("success"):
            error = (
                inventory.get("error", "Could not list database tables.")
                if isinstance(inventory, dict)
                else "Invalid database table inventory response."
            )
            raise RuntimeError(error)

        inventory_result = inventory.get("result", {})
        tables = inventory_result.get("tables", [])
        table_names = [
            item.get("name")
            for item in tables
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
        schema_version = inventory_result.get("schema_version")
        database_identity = inventory_result.get("database")
        database_path = inventory_result.get("database_path")

        evidence.append({
            "tool": "list_database_tables",
            "arguments": {},
            "success": True,
            "result": inventory_result,
        })

        plan = _database_tool_plan(user_text, table_names)
        plan = [item for item in plan if item[0] != "list_database_tables"]

        for tool_name, arguments in plan:
            raw_result = tool_manager.execute(tool_name, arguments)
            try:
                parsed = json.loads(raw_result)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"{tool_name} returned invalid JSON.") from exc

            if not isinstance(parsed, dict) or not parsed.get("success"):
                error = (
                    parsed.get("error", "Unknown tool error.")
                    if isinstance(parsed, dict)
                    else "Invalid tool response."
                )
                raise RuntimeError(f"{tool_name} failed: {error}")

            result = parsed.get("result", {})
            evidence.append({
                "tool": tool_name,
                "arguments": arguments,
                "success": True,
                "result": result,
            })

            logger.info(
                "Database schema tool executed: database=%s database_path=%s schema_version=%s "
                "tool=%s arguments=%s result=%s",
                database_identity,
                database_path,
                schema_version,
                tool_name,
                json.dumps(arguments, ensure_ascii=False, default=str),
                json.dumps(result, ensure_ascii=False, default=str)[:5000],
            )

        logger.info(
            "Database preflight completed: database=%s database_path=%s schema_version=%s tool_count=%s",
            database_identity,
            database_path,
            schema_version,
            len(evidence),
        )
        return evidence, True

    except Exception as exc:
        logger.exception(
            "Database preflight failed: error_type=%s error=%s",
            type(exc).__name__,
            str(exc),
        )
        return [{
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }], False


def _is_explicit_natural_formal_approval(user_text: str) -> bool:
    """Return True only for a standalone affirmative formal-approval command."""
    text = (user_text or "").strip()
    patterns = (
        r"(?:我同意|同意|请|现在)?\s*(?:确认|批准|正式)(?:正式)?立项(?:吧|。|！|!)?",
        r"(?:我同意|同意|请|现在)?\s*(?:确认|批准)\s*创建项目(?:吧|。|！|!)?",
        r"(?:please\s+)?formally\s+approve\s+(?:the\s+)?project[.!]?",
        r"(?:please\s+)?confirm\s+(?:formal\s+)?project\s+approval[.!]?",
    )
    return any(re.fullmatch(pattern, text, flags=re.IGNORECASE) for pattern in patterns)



def _needs_proposal_tools(user_text: str) -> bool:
    """Detect explicit project initiation or proposal-planning requests."""
    import re
    text = user_text.lower()
    patterns = (
        r"\b(new|start|initiate|plan|propose|create|build|develop)\b.{0,60}\b(project|application|system|platform)\b",
        r"\b(project|application|system|platform)\b.{0,60}\b(proposal|plan|scope|milestone|deliverable)\b",
        r"(新建|创建|开发|建设|规划|设计).{0,12}(项目|系统|应用)|(项目|系统|应用).{0,12}(方案|计划|立项)",
    )
    if any(re.search(pattern, text) for pattern in patterns):
        return True
    return bool(re.search(r"\b(update|revise|modify|change)\b.{0,40}\b(proposal|project scope)\b|\b(proposal|project scope)\b.{0,40}\b(update|revise|modify|change)\b|修改|调整|完善.{0,12}(提案|项目方案)|(提案|项目方案).{0,12}(修改|调整|完善)", text, re.IGNORECASE))


def _record_execution_evidence(*, chat_id: str | None, action: str, object_type: str | None, object_id: str | None, status: str, result: dict[str, Any]) -> None:
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO sys_execution_evidence(evidence_id,chat_id,action,object_type,object_id,status,result_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), chat_id, action, object_type, object_id, status,
                 json.dumps(result, ensure_ascii=False, default=str), _now()),
            )
    except Exception:
        logger.exception("Could not persist execution evidence for action=%s", action)


def _active_discussion_proposal_id(chat: dict[str, Any], include_approved: bool = False) -> str | None:
    """Find the latest saved Proposal referenced in this conversation.

    Formal-approval retries may include an already-approved Proposal so the
    lifecycle service can return its existing Project idempotently.
    """
    for message in reversed(chat.get("messages", [])[-30:]):
        content = message.get("content", "") if isinstance(message, dict) else ""
        if not isinstance(content, str):
            continue
        match = re.search(r"Proposal ID\s*[:：]\s*\*{0,2}\s*`?([0-9a-fA-F-]{36})`?", content, re.IGNORECASE)
        if not match:
            continue
        proposal_id = match.group(1)
        try:
            proposal = get_proposal(proposal_id)
        except HTTPException:
            continue
        if include_approved:
            return proposal_id
        if not proposal.get("project_id") and proposal.get("status") not in {"approved", "rejected"}:
            return proposal_id
    return None


def _proposal_tool_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "prepare_project_proposal",
            "description": "Create and save a structured Proposal discussion draft. Capture objective, scope, deliverables, milestones, timeline, risks and assumptions. Do NOT create executable tasks, assign Agents, or create a formal Project. Team staffing is planned separately from the saved Proposal using the registered Specialist catalog.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"}, "objective": {"type": "string"},
                    "scope": {"type": "object"}, "budget": {"type": "object"},
                    "acceptance_criteria": {"type": "array", "items": {}},
                    "deliverables": {"type": "array", "items": {}},
                    "milestones": {"type": "array", "items": {}},
                    "timeline": {"type": "object"},
                    "risks": {"type": "array", "items": {}}, "assumptions": {"type": "array", "items": {}},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                    "baseline_due_date": {"type": "string"}
                },
                "required": ["title", "objective", "scope", "deliverables", "milestones", "timeline", "risks"]
            }
        }
    }


def _proposal_update_tool_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "revise_project_proposal",
            "description": "Revise an existing saved proposal during discussion. Preserve unchanged fields. This invalidates any previously approved Team Plan and does not create a Project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal_id": {"type": "string"}, "title": {"type": "string"},
                    "objective": {"type": "string"}, "scope": {"type": "object"},
                    "budget": {"type": "object"}, "acceptance_criteria": {"type": "array", "items": {}},
                    "deliverables": {"type": "array", "items": {}}, "milestones": {"type": "array", "items": {}},
                    "timeline": {"type": "object"},
                    "risks": {"type": "array", "items": {}}, "assumptions": {"type": "array", "items": {}},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                    "baseline_due_date": {"type": "string"},
                },
                "required": ["proposal_id"], "additionalProperties": False,
            },
        },
    }


def _execute_proposal_update_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    proposal_id = str(arguments.get("proposal_id", "")).strip()
    if not proposal_id:
        raise ValueError("proposal_id is required")
    changes = {key: value for key, value in arguments.items() if key not in {"proposal_id", "budget", "acceptance_criteria"}}
    if "budget" in arguments or "acceptance_criteria" in arguments:
        scope = dict(changes.get("scope") or {})
        if "budget" in arguments:
            scope["budget"] = arguments["budget"]
        if "acceptance_criteria" in arguments:
            scope["acceptance_criteria"] = arguments["acceptance_criteria"]
        changes["scope"] = scope
    updated = update_proposal(proposal_id, ProposalUpdate.model_validate(changes))
    return {"success": True, "proposal": _as_plain_data(updated),
            "message": "Proposal revision saved. Any previous Team Plan approval has been invalidated; regenerate and re-review it when staffing planning resumes."}


def _execute_proposal_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name != "prepare_project_proposal":
        raise ValueError("Unknown proposal tool.")
    validated = ProposalCreate.model_validate(arguments)
    proposal = create_proposal(validated)
    proposal = _as_plain_data(proposal)
    return {
        "proposal": proposal,
        "next_step": "Present the saved Proposal discussion draft. Continue refining it with the Product Owner. Team Planning and Task Planning may proceed independently before or after formal Project Approval. Do not create executable tasks, assign Agents, or dispatch Specialists without the required approvals.",
    }



def _needs_project_tools(user_text: str) -> bool:
    """Expose project-file tools only when the user clearly asks for project work.

    Requiring both an action and a project/file/code reference prevents ordinary
    questions such as “look at this idea” from activating file tools.
    """
    text = user_text.strip().lower()
    if not text:
        return False
    import re

    action_zh = r"查看|看下|看看|检查|浏览|列出|读取|打开|分析|修改|调整|优化|编辑|重写|创建|新建|删除|修复|重构|开发|实现|测试|运行"
    subject_zh = r"项目|代码|文件|目录|文件夹|程序|应用|前端|后端|app|frontend|backend"
    action_en = r"review|inspect|list|read|open|edit|modify|rewrite|create|delete|fix|refactor|implement|test|run|analyze"
    subject_en = r"project|repo|code|file|folder|directory|app|frontend|backend"
    return bool(
        re.search(rf"(?:{action_zh}).{{0,18}}(?:{subject_zh})", text)
        or re.search(rf"(?:{subject_zh}).{{0,18}}(?:{action_zh})", text)
        or re.search(rf"\b(?:{action_en})\b.{{0,40}}\b(?:{subject_en})\b", text)
        or re.search(rf"\b(?:{subject_en})\b.{{0,40}}\b(?:{action_en})\b", text)
    )


def _needs_workspace_file_tools(user_text: str) -> bool:
    text = (user_text or "").lower()
    return bool(re.search(r"\b(file|files|folder|folders|directory|directories|workspace|document|documents)\b.{0,50}\b(list|read|open|create|write|edit|modify|move|rename|delete|copy)\b|\b(list|read|open|create|write|edit|modify|move|rename|delete|copy)\b.{0,50}\b(file|files|folder|folders|directory|directories|workspace|document|documents)\b|文件|文件夹|目录", text))


def _tool_activity_label(name: str, arguments: dict[str, Any], envelope_json: str) -> str:
    path = arguments.get("path", arguments.get("directory", "."))
    try:
        envelope = json.loads(envelope_json)
    except (TypeError, json.JSONDecodeError):
        return f"Tool execution result could not be parsed: {name}"
    if not envelope.get("success"):
        return f"Project operation failed: {path}"
    result = envelope.get("result", {})
    if name == "list_project_files":
        return f"Inspected project directory: {path}"
    if name == "read_project_file":
        return f"Read project file: {path}"
    if name == "write_project_file":
        return f"Wrote project file: {path}" if result.get("written") else f"File write not completed: {path}"
    if name == "replace_project_text":
        return f"Updated project file: {path}" if result.get("updated") else f"File update not completed: {path}"
    if name == "create_task_workspace":
        return f"Created managed workspace: {result.get('workspace_id', 'unknown')}" if result.get("workspace_id") else "Workspace creation not confirmed"
    if name == "write_workspace_output":
        return f"Created and registered Artifact: {result.get('artifact_name', 'unknown')}" if result.get("artifact_id") else "Artifact registration not confirmed"
    if name == "bind_business_context":
        return f"Bound current business context: {result.get('object_type', 'object')} {result.get('object_id', '')}"
    return "Operation executed"


def _normalise_proposal_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert common model-generated proposal field variants to the backend schema."""
    data = dict(payload)
    data["title"] = data.get("title") or data.get("project_name") or "Untitled Project"
    data["objective"] = data.get("objective") or ""
    data["deliverables"] = data.get("deliverables") or []
    data["milestones"] = data.get("milestones") or []
    data["tasks"] = data.get("tasks") or []
    data["risks"] = data.get("risks") or data.get("risk_management") or []
    data["assumptions"] = data.get("assumptions") or []
    data["acceptance_criteria"] = data.get("acceptance_criteria") or []

    scope = data.get("scope", {})
    if isinstance(scope, list):
        data["scope"] = {"items": scope}
    elif isinstance(scope, str):
        data["scope"] = {"description": scope}
    elif not isinstance(scope, dict):
        data["scope"] = {}

    timeline = data.get("timeline")
    if timeline is None:
        summary = data.get("timeline_summary")
        timeline = {"summary": summary} if summary else {}
    elif isinstance(timeline, str):
        timeline = {"summary": timeline}
    elif isinstance(timeline, list):
        timeline = {"milestones": timeline}
    elif not isinstance(timeline, dict):
        timeline = {}
    data["timeline"] = timeline
    if isinstance(data["scope"], dict):
        if isinstance(data.get("budget"), dict):
            data["scope"]["budget"] = data["budget"]
        if data.get("acceptance_criteria"):
            data["scope"]["acceptance_criteria"] = data["acceptance_criteria"]

    tasks = []
    for task in data["tasks"]:
        if isinstance(task, dict):
            task = dict(task)
            if "depends_on" not in task and isinstance(task.get("dependencies"), list):
                task["depends_on"] = task["dependencies"]
        tasks.append(task)
    data["tasks"] = tasks
    return data


def _parse_proposal_payload(content: str) -> dict[str, Any] | None:
    """Recognise and normalise proposal JSON emitted as plain text without tool metadata."""
    decoder = json.JSONDecoder()
    for index, character in enumerate(content):
        if character != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(content[index:])
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        has_title = bool(payload.get("title") or payload.get("project_name"))
        required_content = all(
            key in payload for key in ("objective", "scope", "deliverables", "milestones", "tasks")
        )
        has_timeline = "timeline" in payload or "timeline_summary" in payload
        has_risks = "risks" in payload or "risk_management" in payload
        if has_title and required_content and has_timeline and has_risks and isinstance(payload.get("tasks"), list):
            return _normalise_proposal_payload(payload)
    return None


def _format_proposal_for_chat(arguments: dict[str, Any], tool_result: str) -> str:
    """Render a successfully saved proposal as readable English Markdown."""
    try:
        envelope = json.loads(tool_result)
    except (TypeError, json.JSONDecodeError):
        return "The proposal could not be confirmed as saved. Please check the backend log."

    if not isinstance(envelope, dict) or not envelope.get("success"):
        error = envelope.get("error", "Unknown validation error.") if isinstance(envelope, dict) else "Invalid tool response."
        return ("## Proposal Submission Failed\n\n"
                f"**Reason:** {error}\n\n"
                "No formal project or tasks have been created.")

    result = envelope.get("result", {})
    saved = result.get("proposal") or {}
    if not isinstance(saved, dict):
        saved = {}
    proposal_id = saved.get("id") or saved.get("proposal_id") or "Not returned by the proposal service"
    lines = [
        "## Project Proposal",
        f"### {arguments.get('title', 'Untitled Project')}",
        "",
        "**Status:** Discussion Draft",
        f"**Proposal ID:** {proposal_id}",
        "",
        "### 1. Objective",
        str(arguments.get("objective", "")),
        "",
        "### 2. Scope",
    ]

    scope = arguments.get("scope", {})
    if isinstance(scope, dict):
        for key, value in scope.items():
            if isinstance(value, list):
                lines.append(f"- **{str(key).replace('_', ' ').title()}:**")
                lines.extend(f"  - {item}" for item in value)
            else:
                lines.append(f"- **{str(key).replace('_', ' ').title()}:** {value}")
    elif isinstance(scope, list):
        lines.extend(f"- {item}" for item in scope)
    else:
        lines.append(str(scope))

    sections = [
        ("3. Deliverables", "deliverables"),
        ("4. Milestones", "milestones"),
        ("5. Timeline", "timeline"),
        ("6. Acceptance Criteria", "acceptance_criteria"),
        ("7. Risks", "risks"),
        ("8. Assumptions", "assumptions"),
    ]
    for heading, field in sections:
        value = arguments.get(field)
        if value in (None, [], {}):
            continue
        lines.extend(["", f"### {heading}"])
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("title") or item.get("id") or "Item"
                    details = item.get("description") or item.get("deliverable") or item.get("completion_criteria") or ""
                    agent = item.get("agent")
                    dependencies = item.get("depends_on") or item.get("dependencies") or []
                    suffix = f" — {details}" if details else ""
                    if agent:
                        suffix += f" *(Agent: {agent})*"
                    if dependencies:
                        suffix += f" *(Depends on: {', '.join(map(str, dependencies))})*"
                    lines.append(f"- **{name}**{suffix}")
                else:
                    lines.append(f"- {item}")
        elif isinstance(value, dict):
            for key, item in value.items():
                lines.append(f"- **{str(key).replace('_', ' ').title()}:** {item}")
        else:
            lines.append(str(value))

    lines.extend([
        "",
        "---",
        "This proposal is saved as a discussion draft. You can discuss and refine its objective, scope, deliverables, milestones, risks and assumptions. No formal project, task records or Agent assignments have been created.",
    ])
    if isinstance(proposal_id, str) and len(proposal_id) == 36:
        lines.append(f"To propose a Specialist team, send: `plan team for proposal {proposal_id}`")
        lines.append(f"When ready, formally create the Project independently of Team Plan approval with: `formally approve proposal {proposal_id}`")
        lines.append(f"To reject this proposal, send: `reject proposal {proposal_id}: <reason>`")
    return "\n".join(lines)


def _parse_text_tool_call(content: str, allowed_tools: set[str]) -> tuple[str, dict[str, Any]] | None:
    """Accept a small JSON tool-call fallback for models that don't emit tool_calls."""
    decoder = json.JSONDecoder()
    for index, character in enumerate(content):
        if character != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(content[index:])
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        function = payload.get("function") if isinstance(payload.get("function"), dict) else {}
        name = (payload.get("name") or payload.get("tool") or payload.get("tool_name")
                or payload.get("action") or function.get("name"))
        if name not in allowed_tools:
            continue
        arguments = payload.get("arguments", payload.get("parameters",
                    payload.get("action_input", function.get("arguments", {}))))
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                continue
        if not isinstance(arguments, dict):
            continue
        if not arguments:
            arguments = {key: value for key, value in payload.items() if key not in {"name", "tool", "tool_name", "function", "arguments", "parameters"}}
        return str(name), arguments
    return None




def _project_catalog() -> list[dict[str, str]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name, status FROM sys_projects ORDER BY updated_at DESC"
        ).fetchall()
    return [{"id": str(row["id"]), "name": str(row["name"]), "status": str(row["status"])} for row in rows]


def _resolve_explicit_project_reference(user_text: str) -> tuple[str | None, list[dict[str, str]]]:
    """Bind only an explicit, unambiguous project ID or project-name reference."""
    catalog = _project_catalog()
    lowered = user_text.casefold()
    matches = []
    for item in catalog:
        project_id = item["id"].casefold()
        name = item["name"].strip()
        name_lower = name.casefold()
        id_match = project_id in lowered
        quoted_match = any(
            quote_left + name_lower + quote_right in lowered
            for quote_left, quote_right in (('"', '"'), ("'", "'"), ("“", "”"), ("「", "」"))
        )
        explicit_name_match = bool(name_lower) and (
            re.search(rf"project\s+{re.escape(name_lower)}", lowered) is not None
            or re.search(rf"{re.escape(name_lower)}\s+project", lowered) is not None
            or re.search(rf"{re.escape(name_lower)}\s*项目", lowered) is not None
            or re.search(rf"项目\s*{re.escape(name_lower)}", lowered) is not None
            or (len(name_lower) >= 5 and quoted_match)
        )
        if id_match or explicit_name_match:
            matches.append(item)
    unique_ids = {item["id"] for item in matches}
    if len(unique_ids) == 1:
        return next(iter(unique_ids)), catalog
    return None, catalog

@app.get("/api/chats")
async def list_chats() -> list[dict[str, Any]]:
    return _read_chats()


@app.get("/api/categories")
async def list_categories() -> list[str]:
    return _read_categories()


@app.post("/api/categories")
async def create_category(payload: NewCategory) -> list[str]:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Category name cannot be empty.")
    categories = _read_categories()
    if name not in categories:
        categories.append(name)
        _write_categories(categories)
    return categories


@app.delete("/api/categories/{category_name}")
async def delete_category(category_name: str) -> dict[str, Any]:
    name = category_name.strip()
    if not name or name in {"全部对话", "Uncategorised", "未分类"}:
        raise HTTPException(status_code=400, detail="This category cannot be deleted.")
    categories = _read_categories()
    if name not in categories:
        raise HTTPException(status_code=404, detail="Category not found.")
    # Preserve conversations: move them to the uncategorised bucket.
    chats = _read_chats()
    moved_count = 0
    for chat in chats:
        if chat.get("category") == name:
            chat["category"] = "未分类"
            chat["updated_at"] = _now()
            moved_count += 1
    _write_chats(chats)
    categories = [item for item in categories if item != name]
    _write_categories(categories)
    return {"categories": categories, "moved_conversations": moved_count}


@app.post("/api/categories/rename")
async def rename_category(payload: RenameCategory) -> list[str]:
    old_name, new_name = payload.old_name.strip(), payload.new_name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Category name cannot be empty.")
    categories = _read_categories()
    if old_name not in categories:
        raise HTTPException(status_code=404, detail="Category not found.")
    if new_name != old_name and new_name in categories:
        raise HTTPException(status_code=409, detail="A category with this name already exists.")
    categories = [new_name if name == old_name else name for name in categories]
    _write_categories(categories)
    chats = _read_chats()
    for chat in chats:
        if chat.get("category") == old_name:
            chat["category"] = new_name
    _write_chats(chats)
    return categories


@app.post("/api/chats")
async def create_chat(payload: NewChat) -> dict[str, Any]:
    chats = _read_chats()
    project_name = None
    if payload.project_id:
        with connect() as conn:
            project_row = conn.execute("SELECT name FROM sys_projects WHERE id=?", (payload.project_id,)).fetchone()
            if not project_row:
                raise HTTPException(status_code=404, detail="Project not found.")
            project_name = str(project_row["name"])
    chat = {
        "id": uuid.uuid4().hex,
        "title": "New Chat",
        "category": payload.category.strip() or "Uncategorised",
        "project_id": payload.project_id,
        "project_name": project_name,
        "created_at": _now(),
        "updated_at": _now(),
        "messages": [],
    }
    chats.insert(0, chat)
    _write_chats(chats)
    return chat


@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str) -> dict[str, str]:
    chats = _read_chats()
    remaining = [chat for chat in chats if chat.get("id") != chat_id]
    if len(remaining) == len(chats):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    _write_chats(remaining)
    return {"status": "deleted", "chat_id": chat_id}


@app.patch("/api/chats/{chat_id}")
async def update_chat(chat_id: str, payload: ChatUpdate) -> dict[str, Any]:
    chats, chat = _get_chat(chat_id)
    if payload.title is not None:
        chat["title"] = payload.title.strip() or "New Chat"
    if payload.category is not None:
        chat["category"] = payload.category.strip() or "Uncategorised"
    if "project_id" in payload.model_fields_set:
        if payload.project_id:
            with connect() as conn:
                project_row = conn.execute("SELECT name FROM sys_projects WHERE id=?", (payload.project_id,)).fetchone()
                if not project_row:
                    raise HTTPException(status_code=404, detail="Project not found.")
                chat["project_name"] = str(project_row["name"])
        else:
            chat["project_name"] = None
        chat["project_id"] = payload.project_id
    chat["updated_at"] = _now()
    _write_chats(chats)
    return chat


def _bind_chat_project(chats: list[dict[str, Any]], chat: dict[str, Any], project_id: str) -> None:
    with connect() as conn:
        row = conn.execute("SELECT name FROM sys_projects WHERE id=?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Project not found.")
    chat["project_id"] = project_id
    chat["project_name"] = str(row["name"])
    chat["updated_at"] = _now()
    _write_chats(chats)
    stamp = _now()
    with connect() as conn:
        conn.execute("""INSERT INTO sys_business_contexts(chat_id,object_type,object_id,project_id,context_json,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET object_type='project',object_id=excluded.object_id,
            project_id=excluded.project_id,updated_at=excluded.updated_at""",
            (chat["id"], "project", project_id, project_id, "{}", stamp, stamp))


@app.post("/api/chats/{chat_id}/messages")
async def send_message(chat_id: str, payload: SendMessage) -> dict[str, Any]:
    chats, chat = _get_chat(chat_id)
    text = payload.content.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    user_message = {"role": "user", "content": text, "created_at": _now()}
    chat["messages"].append(user_message)
    tool_activity: list[str] = []
    created_artifacts: list[dict[str, Any]] = []
    if len(chat["messages"]) == 1:
        chat["title"] = text[:28] + ("…" if len(text) > 28 else "")

    # A global chat is bound only when the current message explicitly identifies
    # exactly one formal project. Project-entry chats already carry trusted metadata.
    if not chat.get("project_id"):
        explicit_project_id, available_projects_for_turn = _resolve_explicit_project_reference(text)
        if explicit_project_id:
            chat["project_id"] = explicit_project_id
            matched_project = next((item for item in available_projects_for_turn if item["id"] == explicit_project_id), None)
            chat["project_name"] = matched_project["name"] if matched_project else None
            chat["updated_at"] = _now()
            _write_chats(chats)

    # Persist the trusted project binding and any uniquely identified active Proposal.
    # This supplements chat JSON history; the database remains the business-context source of truth.
    try:
        context_proposal_id = _active_discussion_proposal_id(chat, include_approved=True)
        with connect() as context_conn:
            existing_context = context_conn.execute("SELECT * FROM sys_business_contexts WHERE chat_id=?", (chat_id,)).fetchone()
            if chat.get("project_id") or context_proposal_id:
                context_type = "project" if chat.get("project_id") else "proposal"
                context_id = chat.get("project_id") or context_proposal_id
                context_conn.execute("""INSERT INTO sys_business_contexts(chat_id,object_type,object_id,project_id,proposal_id,context_json,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET
                    object_type=excluded.object_type,object_id=excluded.object_id,
                    project_id=COALESCE(excluded.project_id,sys_business_contexts.project_id),
                    proposal_id=COALESCE(excluded.proposal_id,sys_business_contexts.proposal_id),updated_at=excluded.updated_at""",
                    (chat_id, context_type, context_id, chat.get("project_id"), context_proposal_id, "{}", _now(), _now()))
    except Exception:
        logger.exception("Could not persist Chat business context for chat_id=%s", chat_id)

    # Natural-language formal approval is mapped to the real lifecycle service
    # only when the user gives an explicit affirmative instruction. A discussion
    # about approval, or a request to submit something for review, is not approval.
    natural_formal_approval = _is_explicit_natural_formal_approval(text)

    if natural_formal_approval:
        proposal_id = _active_discussion_proposal_id(chat, include_approved=True)
        if not proposal_id:
            answer = (
                "I cannot identify a single active, saved Proposal in this conversation. "
                "No project was created. Please provide the exact Proposal ID before formal approval."
            )
        else:
            try:
                approval_result = formally_approve_proposal(proposal_id, LifecycleComment(comment="Explicit Product Owner confirmation in chat."))
                project_id = approval_result["project"]["id"]
                _bind_chat_project(chats, chat, project_id)
                _record_execution_evidence(chat_id=chat_id, action="proposal.formal_approve", object_type="proposal", object_id=proposal_id, status="succeeded", result={"project_id": project_id})
                answer = (
                    "Formal project creation completed. The backend confirmed the Project record.\n\n"
                    f"**Proposal ID:** {proposal_id}\n**Project ID:** {project_id}\n\n"
                    "No task records or Agent assignments were created, and execution is not authorised."
                )
            except HTTPException as exc:
                answer = f"Formal project approval could not be completed (HTTP {exc.status_code}): {exc.detail}. No successful transition is claimed."
            except Exception as exc:
                logger.exception("Natural-language formal approval failed. proposal_id=%s", proposal_id)
                answer = f"Formal project approval failed due to a backend error ({type(exc).__name__}). No successful transition is claimed."
    else:
        answer = None

    team_plan_match = None if answer is not None else re.fullmatch(
        r"\s*plan team for proposal\s+([0-9a-fA-F-]{36})\s*",
        text, re.IGNORECASE,
    )
    if answer is not None:
        pass
    elif team_plan_match:
        proposal_id = team_plan_match.group(1)
        try:
            plan = await analyze_proposal_team_plan(proposal_id)
            lines = ["## Proposed Team Plan", f"**Proposal ID:** {proposal_id}", f"**Summary:** {plan.get('project_summary', '')}", ""]
            for stream in plan.get('workstreams', []):
                names = ", ".join(agent.get('agent_name', agent['agent_id']) + (" [blocked]" if agent.get('status') != 'ready' else "") for agent in stream.get('candidate_agents', [])) or "No suitable Agent"
                lines.append(f"- **{stream['name']}** — {stream.get('objective', '')}; candidates: {names}")
                if stream.get('required_capabilities'):
                    lines.append("  - Capabilities: " + ", ".join(item.get('capability_id', '') for item in stream['required_capabilities']))
                if stream.get('required_tools'):
                    lines.append("  - Tools: " + ", ".join(item.get('tool', '') for item in stream['required_tools']))
            lines.extend(["", f"**Configuration gaps:** {len(plan.get('capability_gaps', []))}"])
            for gap in plan.get('capability_gaps', []):
                lines.append(f"- {gap.get('gap_type')}: {gap.get('subject')} — {gap.get('reason')}")
            if not plan.get('capability_gaps'):
                lines.append(f"Review the Proposal, then formally create the Project independently of Team Plan approval with: `formally approve proposal {proposal_id}`")
            else:
                lines.append("Resolve the listed configuration gaps and regenerate the Team Plan before requesting Team Plan approval. Project approval remains a separate decision.")
            answer = "\n".join(lines)
        except HTTPException as exc:
            logger.warning(
                "Proposal team planning was rejected. proposal_id=%s status_code=%s detail=%s",
                proposal_id, exc.status_code, exc.detail,
            )
            answer = f"Team planning action could not be completed (HTTP {exc.status_code}): {exc.detail}"
        except Exception as exc:
            # Keep an unexpected planner/registry/database error inside the chat response.
            # Without this guard, the chat request escapes as an unhandled 500 and the
            # frontend only shows its generic delivery-failed state.
            logger.exception(
                "Unexpected Proposal Team Planning failure. proposal_id=%s error_type=%s error=%s",
                proposal_id, type(exc).__name__, str(exc),
            )
            answer = (
                "Team planning failed because the backend encountered an unexpected error. "
                f"Error type: {type(exc).__name__}. Check backend.log for the traceback, "
                "then retry the same Proposal command. No Project, Task or Agent assignment was created."
            )
    else:
        governance_match = re.fullmatch(
            r"\s*(authorize planning for proposal|formally approve proposal|authorize execution for project)\s+([0-9a-fA-F-]{36})(?:\s*[:—-]\s*(.*))?\s*",
            text, re.IGNORECASE,
        )
        if governance_match:
            command, entity_id, comment = governance_match.groups()
            try:
                action = command.lower()
                if action.startswith("authorize planning"):
                    result = authorize_planning(entity_id, LifecycleComment(comment=comment or ""))
                    answer = ("Planning is now authorised for proposal discussion and Team Planning. "
                              "This does not create a formal project or authorise execution.")
                elif action.startswith("formally approve"):
                    result = formally_approve_proposal(entity_id, LifecycleComment(comment=comment or ""))
                    project_id = result["project"]["id"]
                    _bind_chat_project(chats, chat, project_id)
                    _record_execution_evidence(chat_id=chat_id, action="proposal.formal_approve", object_type="proposal", object_id=entity_id, status="succeeded", result={"project_id": project_id})
                    answer = (
                        "Formal project creation completed. The Project record has been written to the database. "
                        "No task records or Agent assignments were created in this release, and execution is not authorised.\n\n"
                        f"Project ID: {project_id}"
                    )
                else:
                    result = authorize_project_execution(entity_id)
                    answer = "Execution is explicitly authorised. This command is reserved for the execution release and does not create or assign tasks."
            except HTTPException as exc:
                answer = f"Governance action could not be completed: {exc.detail}"
        else:
            decision_match = re.fullmatch(r"\s*(approve proposal|reject proposal|request changes for proposal|resubmit proposal)\s+([0-9a-fA-F-]{36})(?:\s*[:—-]\s*(.*))?\s*", text, re.IGNORECASE)
            if decision_match:
                command, proposal_id, comment = decision_match.groups()
                try:
                    if command.lower().startswith("approve"):
                        result = formally_approve_proposal(proposal_id, LifecycleComment(comment=comment or ""))
                        _bind_chat_project(chats, chat, result["project"]["id"])
                        _record_execution_evidence(chat_id=chat_id, action="proposal.formal_approve", object_type="proposal", object_id=proposal_id, status="succeeded", result={"project_id": result["project"]["id"]})
                        answer = ("Formal project creation completed. The Project record has been written to the database. "
                                  "No task records or Agent assignments were created in this release, and execution is not authorised.\n\n"
                                  f"Project ID: {result['project']['id']}")
                    elif command.lower().startswith("resubmit"):
                        result = resubmit_proposal(proposal_id)
                        answer = f"Proposal {proposal_id} returned to discussion. Regenerate the Team Plan after changes."
                    else:
                        action = "reject" if command.lower().startswith("reject") else "request_changes"
                        result = decide_proposal(proposal_id, ProposalDecision(action=action, comment=comment or ""))
                        answer = f"Proposal status updated: {result['status']}."
                except HTTPException as exc:
                    answer = f"Proposal decision could not be completed: {exc.detail}"
            elif text.startswith("/search") or text.startswith("/搜索"):
                command = "/search" if text.startswith("/search") else "/搜索"
                query = text.removeprefix(command).strip()
                tool_result = await _search_web(query) if query else "Please provide a search query after /search."
                answer = f"Search results:\n\n{tool_result}"
            else:
                selected_model = _main_agent_config()["model"]
                project_settings = _project_settings()
                project_mode = _needs_project_tools(text)
                active_proposal_id = _active_discussion_proposal_id(chat)
                proposal_mode = _needs_proposal_tools(text) or bool(active_proposal_id)
                management_mode = _needs_management_tools(text)
                management_modify_mode = _needs_management_mutations(text)
                database_mode = _needs_database_tools(text)
                database_modify_mode = _needs_database_modify(text)
                search_mode = _needs_search_tools(text)
                workspace_file_mode = _needs_workspace_file_tools(text)
                workspace_output_mode = bool(re.search(r"导出|输出文件|生成文件|下载|excel|xlsx|csv|spreadsheet|export|save (?:as|to)|generate (?:a )?(?:file|report|document)", text, re.IGNORECASE))
                prompt_update_requested = bool(re.search(
                    r"(project prompt|p4|项目提示词|项目指令).{0,30}(update|revise|change|修改|更新|调整)|(update|revise|change|修改|更新|调整).{0,30}(project prompt|p4|项目提示词|项目指令)",
                    text,
                    flags=re.IGNORECASE,
                ))
                intent = classify_intent(
                    text,
                    project_tools=(project_mode or prompt_update_requested or workspace_file_mode),
                    proposal_tools=proposal_mode,
                    management_tools=management_mode,
                    database_tools=database_mode,
                    web_search=search_mode,
                )
                configured_tool_catalog = ToolRegistry(TOOL_REGISTRY_FILE).list_tools()
                custom_tool_query = bool(configured_tool_catalog) and bool(re.search(
                    r"\b(search|look up|query|retrieve)\b|搜索|查询|查找|检索", text, flags=re.IGNORECASE
                ))
                if custom_tool_query and intent.mode == "direct_response":
                    intent = replace(intent, mode="tool_query", reason="request matches configured API Tool operation")
                logger.info("Main Agent intent route: %s", json.dumps(intent.to_dict(), ensure_ascii=False))
                tool_manager = ToolManager()
                register_business_context_tool(
                    tool_manager, chat_id=chat_id,
                    on_project_bound=lambda selected_project_id: _bind_chat_project(chats, chat, selected_project_id),
                )
                if workspace_output_mode or project_mode:
                    register_workspace_tools(tool_manager, chat_id=chat_id, project_id=chat.get("project_id"))
                agent_registry = AgentRegistry(config_path=SPECIALIST_AGENTS_FILE)
                agent_dispatcher = AgentDispatcher(
                    agent_registry,
                    AgentRuntime(OLLAMA_BASE_URL, selected_model),
                )
                dispatch_schema = {
                    "type": "function",
                    "function": {
                        "name": "delegate_to_specialist",
                        "description": "Dispatch a bounded task to one registered Specialist Agent. This is Agent orchestration, not a general-purpose tool call. Use when specialist expertise is needed.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "agent_id": {"type": "string", "enum": [a["agent_id"] for a in agent_registry.list_agents() if a["enabled"]], "description": "Choose one enabled, preconfigured Specialist Agent. Available profiles: " + "; ".join(f"{a['agent_id']}: {', '.join(a.get('capability_labels', a['capabilities'])) or a['display_name']}; task types: {', '.join(a['allowed_task_types']) or 'as described in role instructions'}" for a in agent_registry.list_agents() if a["enabled"])},
                                "task": {"type": "string", "description": "A specific, actionable task with an expected output."},
                                "context": {"type": "string", "description": "Relevant context and constraints to pass to the specialist."},
                                "task_id": {"type": "string", "description": "Optional persisted project task ID."}
                            },
                            "required": ["agent_id", "task"]
                        }
                    }
                }
                project_tools = _project_tool_schemas(project_settings) if project_mode else []
                if workspace_file_mode and project_settings.get("read_enabled", False):
                    authorised_root = Path(project_settings["project_root"]).resolve()
                    register_file_tools(tool_manager, WorkspaceFileManager(authorised_root, STATE_DIR), allow_write=bool(project_settings.get("write_enabled", False)))
                enabled_specialists = [a for a in agent_registry.list_agents() if a["enabled"]]
                if intent.allow_agent_delegation and enabled_specialists:
                    project_tools.append(dispatch_schema)
                if chat.get("project_id") and prompt_update_requested:
                    project_tools.append({
                        "type": "function",
                        "function": {
                            "name": "propose_project_prompt_update",
                            "description": "Create a new draft version of the current project's P4 Project Prompt for Product Owner review. Never activates the draft.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "content": {"type": "string", "description": "Complete proposed Project Prompt content."},
                                    "change_summary": {"type": "string", "description": "Reason and summary of the proposed changes."}
                                },
                                "required": ["content", "change_summary"]
                            }
                        }
                    })
                if proposal_mode:
                    explicit_new_proposal = bool(re.search(r"\b(new|create|start|initiate)\b.{0,50}\b(project|proposal)\b|新建|创建.{0,10}(项目|提案)", text, re.IGNORECASE))
                    if not active_proposal_id or explicit_new_proposal:
                        project_tools.append(_proposal_tool_schema())
                    if active_proposal_id:
                        project_tools.append(_proposal_update_tool_schema())
                if management_mode:
                    project_tools.extend(_management_tool_schemas(include_mutations=management_modify_mode))
                # Main Agent receives the Search capability when the user explicitly asks for current/web information.
                if search_mode:
                    async def google_search_handler(args):
                        query = str(args.get("query", "")).strip()
                        if not query:
                            raise ValueError("A search query is required.")
                        return {"query": query, "results": await _search_web(query), "configured": bool(SERPAPI_API_KEY)}
                    tool_manager.register(
                        "google_search",
                        "Search the public web through the configured Google Search provider. Use for current information, documentation and news. This capability is available to Main Agent; Specialist internet access is not automatic.",
                        {"type": "object", "properties": {"query": {"type": "string", "description": "What to search for"}}, "required": ["query"], "additionalProperties": False},
                        google_search_handler,
                    )

                # Owner-configured API tools are exposed only for Tool Query turns.
                # They are never loaded as arbitrary Python code.
                if intent.mode == "tool_query":
                    configured_registry = ToolRegistry(TOOL_REGISTRY_FILE)
                    for configured_tool in configured_registry.list_tools():
                        if not configured_tool.get("enabled"):
                            continue
                        function_schema = {
                            "type": "function",
                            "function": {
                                "name": configured_tool["function_name"],
                                "description": configured_tool["description"],
                                "parameters": {
                                    "type": "object",
                                    "properties": configured_tool.get("parameters", {}),
                                    "required": configured_tool.get("required", []),
                                    "additionalProperties": False,
                                },
                            },
                        }
                        async def configured_handler(args, item=configured_tool, registry=configured_registry):
                            return await registry.execute(item, args)
                        tool_manager.register_schema(function_schema, configured_handler)

                database_evidence: list[dict[str, Any]] = []
                database_preflight_ok = True

                if database_mode:
                    register_database_tools(tool_manager)
                    register_sqlite_operation_tools(tool_manager, allow_modify=database_modify_mode)
                    database_evidence, database_preflight_ok = _execute_database_preflight(
                        tool_manager, text
                    )

                for schema in project_tools:
                    tool_name = schema.get("function", {}).get("name", "")
                    if tool_name == "delegate_to_specialist":
                        handler = lambda args: {"success": False, "error": "Specialist dispatch must be handled by AgentDispatcher."}
                    elif tool_name == "prepare_project_proposal":
                        handler = lambda args, n=tool_name: _execute_proposal_tool(n, _normalise_proposal_payload(args))
                    elif tool_name == "revise_project_proposal":
                        handler = lambda args: _execute_proposal_update_tool(args)
                    elif tool_name == "propose_project_prompt_update":
                        handler = lambda args, pid=chat.get("project_id"): update_project_prompt(
                            pid, str(args.get("content", "")), str(args.get("change_summary", "Proposed by Main Agent"))
                        )
                    elif tool_name in {"list_projects", "list_available_agents", "list_project_tasks", "create_project_task", "assign_task_agent", "update_project_task", "add_task_dependency"}:
                        handler = lambda args, n=tool_name: _execute_management_tool(n, args)
                    else:
                        handler = lambda args, n=tool_name: _execute_project_tool(n, args)
                    tool_manager.register_schema(schema, handler)

                context_parts = []
                for relative in payload.context_files:
                    path = _workspace_path(relative)
                    if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
                        continue
                    try:
                        file_text = path.read_text(encoding="utf-8", errors="replace")[:MAX_CONTEXT_CHARS_PER_FILE]
                        context_parts.append(f"\n\n--- File: {relative} ---\n{file_text}")
                    except OSError:
                        continue

                prompt_content = text
                if context_parts:
                    prompt_content += "\n\nThe following files were added to the context for this turn:" + "".join(context_parts)
                prompt_content = "# P6 — Current User Request\n\n" + prompt_content

                recent = chat["messages"][-16:]
                linked_project_id = chat.get("project_id")
                available_projects = _project_catalog() if not linked_project_id else []
                if linked_project_id:
                    try:
                        existing_prompt = get_project_prompt(linked_project_id)
                        if existing_prompt.get("status") == "missing":
                            with connect() as conn:
                                project_row = conn.execute("SELECT * FROM sys_projects WHERE id=?", (linked_project_id,)).fetchone()
                            if project_row:
                                initialise_project_prompt(linked_project_id, dict(project_row), {})
                    except (OSError, ValueError) as exc:
                        raise HTTPException(status_code=409, detail=f"Project Prompt could not be loaded: {exc}") from exc

                runtime_environment = build_runtime_environment(
                    agent_id="main_agent",
                    model=selected_model,
                    available_tools=tool_manager.names(),
                    allowed_tools=tool_manager.names(),
                    workspace_root=WORKSPACE,
                    project_root=project_settings["project_root"],
                    read_enabled=project_settings["read_enabled"],
                    write_enabled=project_settings["write_enabled"],
                    ollama_base_url=OLLAMA_BASE_URL,
                )
                persisted_business_context = None
                with connect() as context_conn:
                    context_row = context_conn.execute("SELECT * FROM sys_business_contexts WHERE chat_id=?", (chat_id,)).fetchone()
                if context_row:
                    persisted_business_context = dict(context_row)
                    for context_key in ("context_json", "last_result_json", "pending_decision_json"):
                        raw_context = persisted_business_context.pop(context_key, None)
                        persisted_business_context[context_key.removesuffix("_json")] = json.loads(raw_context) if raw_context else None
                business_context_prompt = (
                    "\n\nPERSISTED BUSINESS CONTEXT (Backend source of truth):\n" +
                    json.dumps(persisted_business_context, ensure_ascii=False, default=str)
                    if persisted_business_context else
                    "\n\nPERSISTED BUSINESS CONTEXT: No business object is currently bound to this Chat. Do not infer one from unrelated conversations."
                )
                base_system_prompt = assemble_main_agent_prompt(
                    project_context={
                        "project_root": project_settings["project_root"],
                        "read_enabled": project_settings["read_enabled"],
                        "write_enabled": project_settings["write_enabled"],
                    },
                    session_context=build_session_context(
                        conversation_id=chat_id,
                        model=selected_model,
                        context_files=payload.context_files,
                        project_id=chat.get("project_id"),
                    ),
                    agent_catalog=agent_registry.list_agents(),
                    project_id=chat.get("project_id"),
                    project_catalog=None if chat.get("project_id") else available_projects,
                    runtime_environment=runtime_environment,
                ) + business_context_prompt
                runtime_evidence_contract = (
                    "\n\nRUNTIME EVIDENCE CONTRACT — HARD RESPONSE CONSTRAINTS\n"
                    "You may describe only UI controls, buttons, menus, pages, routes, URLs, files, identifiers, "
                    "records, dates, and actions that are explicitly present in current-turn runtime context or "
                    "returned by a tool/service in this turn. Never invent a button, link, endpoint, file path, "
                    "Project ID, Proposal ID, status, deadline, notification, or completion event. "
                    "A suggested command is not an executed action. A draft in chat is not a saved record. "
                    "A tool call is not successful until its result explicitly confirms success. "
                    "If the UI has no control for an action, say that no such control is available; do not invent "
                    "a workaround file or pretend to click it. If no backend action exists, state that limitation "
                    "and do not simulate the action. Use dates only when supplied by the user or runtime; otherwise "
                    "use relative durations or mark dates as undecided. These constraints apply even in direct-response mode."
                )
                project_capabilities = (
                    f"\nMAIN AGENT ROUTING MODE: {intent.mode}. Routing reason: {intent.reason}. "
                    "Use only the capability classes enabled for this turn. A Tool is not an Agent. "
                    "Do not delegate unless delegate_to_specialist is explicitly available. "
                    f"\nConnected project directory: {project_settings['project_root']}. "
                    f"Read access: {'enabled' if project_settings['read_enabled'] else 'disabled'}; "
                    f"Write access: {'enabled' if project_settings['write_enabled'] else 'disabled'}. "
                    "When a user selects a specific Proposal/Project from a query result, resolve the exact database ID and call bind_business_context before proceeding; do not rely on chat-history text alone. Use only tools supplied in this turn. For one-off exports or generated text files without a formal Project, call create_task_workspace first, then write_workspace_output; this creates and registers a real downloadable Artifact. For formal Project work, the workspace tool binds to the current Project. Do not claim a file exists until write_workspace_output returns success. Read relevant files before editing. Report success only when a tool confirms it. "
                    "Do not run terminal commands or assume unavailable tools. If standard tool_calls are unavailable, request a tool using a single-line JSON object with the exact tool name and complete arguments object."
                ) if project_mode or prompt_update_requested or proposal_mode or management_mode or database_mode or intent.allow_agent_delegation or workspace_output_mode else (
                    f"\nMAIN AGENT ROUTING MODE: {intent.mode}. Routing reason: {intent.reason}. "
                    "Answer directly. Do not invent tool execution or Agent dispatch."
                )
                if database_mode:
                    project_capabilities += (
                        "\\nDatabase schema inspection was executed by the backend before this model request. "
                        "The JSON below contains the current-turn database tool evidence. "
                        "Use it as the sole source of database facts. Do not use chat history, model knowledge, "
                        "or assumptions to fill gaps. Do not invent table names, columns, data types, constraints, "
                        "indexes, foreign keys, or SQL. If requested information is absent, explicitly say it was "
                        "not returned by the database tools. Do not claim another tool was executed unless its "
                        "result appears below. "
                        "\\n\\nCURRENT DATABASE TOOL EVIDENCE:\\n"
                        + json.dumps(database_evidence, ensure_ascii=False, indent=2, default=str)
                    )
                model_messages = [
                    {"role": "system", "content": base_system_prompt + runtime_evidence_contract + project_capabilities},
                    *[{"role": item["role"], "content": item["content"]} for item in recent[:-1]],
                    {"role": "user", "content": prompt_content},
                ]
                empty_response_retries = 0
                try:
                    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0)) as client:
                        for _ in range(6):
                            request_body = {"model": selected_model, "messages": model_messages, "stream": False}
                            available_tool_schemas = tool_manager.schemas()
                            if available_tool_schemas:
                                request_body["tools"] = available_tool_schemas
                                request_body["tool_choice"] = "auto"
                            response = await client.post(
                                f"{OLLAMA_BASE_URL}/chat/completions",
                                headers={"Authorization": "Bearer ollama"},
                                json=request_body,
                            )
                            response.raise_for_status()
                            response_payload = response.json()
                            choices = response_payload.get("choices") if isinstance(response_payload, dict) else None
                            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                                raise ValueError("Model response did not contain a valid choices[0] object.")
                            assistant_result = choices[0].get("message")
                            if not isinstance(assistant_result, dict):
                                raise ValueError("Model response choices[0].message was missing or invalid.")
                            calls = assistant_result.get("tool_calls") or []
                            text_call = None
                            if not calls:
                                content = assistant_result.get("content") or ""
                                text_call = _parse_text_tool_call(content, set(tool_manager.names()))
                                if not text_call and proposal_mode:
                                    proposal_payload = _parse_proposal_payload(content)
                                    if proposal_payload is not None:
                                        text_call = ("prepare_project_proposal", proposal_payload)
                                if not text_call:
                                    if not content.strip():
                                        if empty_response_retries < 1:
                                            empty_response_retries += 1
                                            model_messages.append({"role": "assistant", "content": ""})
                                            model_messages.append({"role": "user", "content": "Your previous response was empty. Please provide a concise text answer or invoke an available tool if required. Do not return an empty message."})
                                            continue
                                        answer = "The model returned an empty response twice. No answer or specialist execution was produced. Check the selected model and backend logs."
                                    else:
                                        answer = content
                                    break
                                name, arguments = text_call
                                calls = [{"id": f"text-tool-{uuid.uuid4().hex}", "type": "function", "function": {"name": name, "arguments": arguments}}]
                                model_messages.append({"role": "assistant", "content": content})
                            else:
                                model_messages.append({"role": "assistant", "content": assistant_result.get("content") or "", "tool_calls": calls})
                            for call in calls:
                                call_id = call.get("id", "")
                                function = call.get("function", {})
                                name = function.get("name", "")
                                raw_arguments = function.get("arguments", {})
                                if isinstance(raw_arguments, str):
                                    try:
                                        arguments = json.loads(raw_arguments)
                                    except json.JSONDecodeError:
                                        arguments = {}
                                else:
                                    arguments = raw_arguments if isinstance(raw_arguments, dict) else {}
                                if name == "prepare_project_proposal":
                                    arguments = _normalise_proposal_payload(arguments)
                                logger.info(
                                    "Main Agent tool call: name=%s arguments=%s",
                                    name, json.dumps(arguments, ensure_ascii=False, default=str)[:1000],
                                )
                                if name == "delegate_to_specialist":
                                    dispatch_project_id = chat.get("project_id")
                                    if dispatch_project_id and not is_project_execution_authorized(dispatch_project_id):
                                        result = json.dumps({
                                            "success": False,
                                            "error": "Specialist execution requires both Product Owner execution authorisation and an Active Project Prompt (P4). Please complete both approvals before dispatch."
                                        }, ensure_ascii=False)
                                    else:
                                        specialist_context = str(arguments.get("context", ""))
                                        if chat.get("project_id"):
                                            try:
                                                project_snapshot = get_project(chat["project_id"])
                                                task_snapshot = list_project_tasks(chat["project_id"])
                                                specialist_context += "\n\nREAD-ONLY PROJECT CONTEXT (provided by Main Agent):\n" + json.dumps({"project": _as_plain_data(project_snapshot), "tasks": _as_plain_data(task_snapshot)}, ensure_ascii=False, default=str)[:18000]
                                            except Exception as context_error:
                                                logger.warning("Could not attach read-only project context to Specialist: %s", context_error)
                                        result = json.dumps(
                                            await agent_dispatcher.dispatch(
                                                agent_id=str(arguments.get("agent_id", "")),
                                                task=str(arguments.get("task", "")),
                                                context=specialist_context,
                                                project_id=chat.get("project_id"),
                                                conversation_id=chat_id,
                                                task_id=str(arguments.get("task_id", "")) or None,
                                            ),
                                            ensure_ascii=False,
                                        )
                                else:
                                    result = await tool_manager.execute_async(name, arguments)
                                try:
                                    parsed_tool_result = json.loads(result)
                                    tool_success = parsed_tool_result.get("success", True) if isinstance(parsed_tool_result, dict) else True
                                    if name == "write_workspace_output" and isinstance(parsed_tool_result, dict) and parsed_tool_result.get("success"):
                                        artifact_data = parsed_tool_result.get("result", {})
                                        if artifact_data.get("artifact_id") and artifact_data.get("download_url"):
                                            created_artifacts.append({key: artifact_data.get(key) for key in ("artifact_id", "workspace_id", "artifact_name", "artifact_type", "file_size", "status", "download_url")})
                                    logger.info(
                                        "Main Agent tool result: name=%s success=%s result_preview=%s",
                                        name, tool_success, json.dumps(parsed_tool_result, ensure_ascii=False, default=str)[:1500],
                                    )
                                except Exception:
                                    logger.info("Main Agent tool result: name=%s result_preview=%s", name, str(result)[:1500])
                                if name == "prepare_project_proposal":
                                    answer = _format_proposal_for_chat(arguments, result)
                                elif name == "revise_project_proposal":
                                    try:
                                        update_result = json.loads(result)
                                        answer = (f"Proposal {arguments.get('proposal_id')} has been updated and saved. "
                                                  "Its previous Team Plan approval is now stale; regenerate and re-review the Team Plan when staffing planning resumes. Formal Project Approval remains independent.") if update_result.get("success") else f"Proposal update failed: {update_result.get('error', 'Unknown error')}"
                                    except json.JSONDecodeError:
                                        answer = "Proposal update result could not be confirmed. Check the proposal record before proceeding."
                                if name in {"write_project_file", "replace_project_text", "read_project_file", "list_project_files", "workspace_list", "workspace_read", "workspace_write", "workspace_create_directory", "workspace_move", "workspace_rename", "workspace_delete", "create_task_workspace", "write_workspace_output", "bind_business_context", "sqlite_query", "sqlite_modify", "google_search"}:
                                    tool_activity.append(_tool_activity_label(name, arguments, result))
                                if name == "delegate_to_specialist":
                                    tool_activity.append(f"Specialist dispatch: {arguments.get('agent_id', 'unknown')}")
                                if name == "prepare_project_proposal":
                                    # Proposal is saved and rendered by the backend; do not expose raw JSON.
                                    break
                                if text_call:
                                    model_messages.append({"role": "user", "content": f"Tool result: {result}\nContinue with the user request. If another tool is needed, return a single-line JSON tool request with complete arguments; otherwise provide a concise response."})
                                else:
                                    model_messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
                            if calls and any(call.get("function", {}).get("name") == "prepare_project_proposal" for call in calls):
                                break
                        else:
                            answer = "The tool-call limit for this turn has been reached. " + (f"Last action: {tool_activity[-1]}" if tool_activity else "Please provide a more specific request.")
                except httpx.HTTPStatusError as exc:
                    upstream_response = exc.response
                    try:
                        response_body = upstream_response.text[:4000]
                    except Exception:
                        response_body = "<unable to read upstream response body>"

                    logger.exception(
                        "Chat request failed with upstream HTTP status. "
                        "model=%s ollama_url=%s status_code=%s response_body=%r",
                        selected_model,
                        OLLAMA_BASE_URL,
                        upstream_response.status_code,
                        response_body,
                    )
                    chat["messages"].pop()
                    raise HTTPException(
                        status_code=502,
                        detail=(
                            f"Ollama returned HTTP {upstream_response.status_code} "
                            f"for model {selected_model}. Check backend.log for details."
                        ),
                    ) from exc
                except httpx.TimeoutException as exc:
                    logger.exception(
                        "Chat request timed out. model=%s ollama_url=%s error=%s",
                        selected_model,
                        OLLAMA_BASE_URL,
                        str(exc),
                    )
                    chat["messages"].pop()
                    raise HTTPException(
                        status_code=504,
                        detail=(
                            f"The local Ollama request timed out (model: {selected_model}). "
                            "Check backend.log for details."
                        ),
                    ) from exc
                except Exception as exc:
                    logger.exception(
                        "Chat request failed unexpectedly. model=%s ollama_url=%s "
                        "error_type=%s error=%s",
                        selected_model,
                        OLLAMA_BASE_URL,
                        type(exc).__name__,
                        str(exc),
                    )
                    chat["messages"].pop()
                    raise HTTPException(
                        status_code=502,
                        detail=(
                            f"Chat request failed (model: {selected_model}, "
                            f"{type(exc).__name__}: {exc}）。"
                            "Check backend.log for the full exception details."
                        ),
                    ) from exc

                if database_mode and not database_preflight_ok:
                    failure = (
                        database_evidence[0].get("error", "Unknown database inspection error.")
                        if database_evidence else "No database evidence was returned."
                    )
                    answer = (
                        "## Database Inspection Failed\\n\\n"
                        f"{failure}\\n\\n"
                        "No database schema facts have been verified. "
                        "Please check the database connection and backend log."
                    )

                completed_writes = [item for item in tool_activity if "Project file written:" in item]
                if completed_writes and any(phrase in answer for phrase in ("need more tools", "reached the 6-call limit", "no text was returned")):
                    changed_paths = [item.split(" — ", 1)[0].split(": ", 1)[-1] for item in completed_writes]
                    answer = "Changes completed: " + ", ".join(dict.fromkeys(changed_paths)) + ". Original files were backed up automatically."

    # Persist and return the response for every route, including deterministic
    # governance actions. Previously this block was nested inside the LLM-only
    # branch, causing formal approval to fall through and return None (HTTP 500).
    assistant_message = {"role": "assistant", "content": answer, "created_at": _now()}
    saved_proposal_match = re.search(r"Proposal ID\s*[:：]\s*\*{0,2}\s*`?([0-9a-fA-F-]{36})", answer or "", re.IGNORECASE)
    if saved_proposal_match:
        saved_proposal_id = saved_proposal_match.group(1)
        try:
            saved_proposal = get_proposal(saved_proposal_id)
            if not saved_proposal.get("project_id") and saved_proposal.get("status") not in {"rejected", "approved"}:
                assistant_message["ui_confirmation"] = _proposal_confirmation_payload(saved_proposal)
                assistant_message["ui_actions"] = [
                    {"type": "proposal.team_plan", "label": "Start Team Planning", "proposal_id": saved_proposal_id},
                    {"type": "proposal.formal_approve", "label": "Confirm this Proposal and create Project", "proposal_id": saved_proposal_id,
                     "proposal_title": saved_proposal.get("title", "Untitled Proposal"),
                     "snapshot_hash": assistant_message["ui_confirmation"]["snapshot_hash"]},
                ]
        except HTTPException:
            logger.warning("Saved proposal action card omitted because proposal lookup failed: %s", saved_proposal_id)
    if not (text.startswith("/search") or text.startswith("/搜索")) and tool_activity:
        assistant_message["actions"] = tool_activity
    if created_artifacts:
        assistant_message["artifacts"] = created_artifacts
    chat["messages"].append(assistant_message)
    chat["updated_at"] = _now()
    _write_chats(chats)
    return {"chat": chat, "answer": answer}


def _proposal_snapshot(proposal: dict[str, Any]) -> dict[str, Any]:
    """Return the exact user-reviewable fields of a persisted Proposal."""
    fields = (
        "id", "title", "objective", "scope", "deliverables", "milestones",
        "tasks", "agent_allocations", "timeline", "risks", "assumptions",
        "priority", "baseline_due_date", "updated_at",
    )
    return {key: proposal.get(key) for key in fields}


def _proposal_snapshot_hash(proposal: dict[str, Any]) -> str:
    canonical = json.dumps(_proposal_snapshot(proposal), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _proposal_confirmation_payload(proposal: dict[str, Any]) -> dict[str, Any]:
    """Build a UI confirmation card from persisted data, never from model prose."""
    snapshot = _proposal_snapshot(proposal)
    return {
        "kind": "proposal_confirmation",
        "proposal_id": proposal["id"],
        "snapshot_hash": _proposal_snapshot_hash(proposal),
        "updated_at": proposal.get("updated_at"),
        "status": proposal.get("status"),
        "title": proposal.get("title"),
        "objective": proposal.get("objective"),
        "scope": proposal.get("scope") or {},
        "deliverables": proposal.get("deliverables") or [],
        "milestones": proposal.get("milestones") or [],
        "tasks": proposal.get("tasks") or [],
        "timeline": proposal.get("timeline") or {},
        "risks": proposal.get("risks") or [],
        "assumptions": proposal.get("assumptions") or [],
        "priority": proposal.get("priority"),
        "baseline_due_date": proposal.get("baseline_due_date"),
        "snapshot_fields": list(snapshot.keys()),
    }


@app.post("/api/chats/{chat_id}/actions")
async def execute_chat_action(chat_id: str, payload: ChatActionRequest) -> dict[str, Any]:
    """Execute a small, explicit allowlist of chat-card actions."""
    chats, chat = _get_chat(chat_id)
    proposal_id = payload.proposal_id.strip()
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", proposal_id):
        raise HTTPException(status_code=400, detail="Invalid Proposal ID.")
    active_id = _active_discussion_proposal_id(chat, include_approved=True)
    if active_id != proposal_id:
        raise HTTPException(status_code=409, detail="This Proposal is not associated with the active conversation context.")

    if payload.action == "proposal.formal_approve":
        current_proposal = get_proposal(proposal_id)
        current_hash = _proposal_snapshot_hash(current_proposal)
        if not payload.snapshot_hash:
            raise HTTPException(status_code=400, detail="The confirmation card is missing its Proposal content fingerprint. Refresh the Proposal before approving.")
        if payload.snapshot_hash != current_hash:
            raise HTTPException(status_code=409, detail="This Proposal changed after the confirmation card was displayed. Review the latest Proposal content before approving.")
        result = formally_approve_proposal(
            proposal_id, LifecycleComment(comment="Explicit Product Owner approval through the chat action card.")
        )
        project = result.get("project", {})
        project_id = project.get("id")
        if project_id:
            _bind_chat_project(chats, chat, project_id)
            _record_execution_evidence(chat_id=chat_id, action="proposal.formal_approve", object_type="proposal", object_id=proposal_id, status="succeeded", result={"project_id": project_id, "source": "chat_action_card"})
        if not project_id:
            raise HTTPException(status_code=502, detail="Approval service did not return a Project ID.")
        chat["project_id"] = project_id
        chat["project_name"] = project.get("name")
        user_text = "Approved the proposal for formal project creation using the chat action card."
        answer = (
            "Formal project creation completed. The Backend confirmed the Project record.\n\n"
            f"**Proposal ID:** {proposal_id}\n**Project ID:** {project_id}\n\n"
            "Team Planning and Task Planning remain separate. Execution is not authorised."
        )
        next_actions = []
    elif payload.action == "proposal.team_plan":
        plan = await analyze_proposal_team_plan(proposal_id)
        user_text = "Started Team Planning using the chat action card."
        answer = (
            "## Proposed Team Plan\n\n"
            f"**Proposal ID:** {proposal_id}\n"
            f"**Summary:** {plan.get('project_summary', '')}\n\n"
            f"**Workstreams:** {len(plan.get('workstreams', []))}\n"
            f"**Configuration gaps:** {len(plan.get('capability_gaps', []))}\n\n"
            "Review the generated Team Plan before approving it."
        )
        next_actions = [{"type": "proposal.formal_approve", "label": "Formal Project Approval", "proposal_id": proposal_id}]
    else:
        raise HTTPException(status_code=400, detail="Unsupported chat action.")

    chat["messages"].append({"role": "user", "content": user_text, "created_at": _now()})
    assistant_message = {"role": "assistant", "content": answer, "created_at": _now()}
    if next_actions:
        assistant_message["ui_actions"] = next_actions
    chat["messages"].append(assistant_message)
    chat["updated_at"] = _now()
    _write_chats(chats)
    return {"chat": chat, "result": result if payload.action == "proposal.formal_approve" else {"success": True}}


@app.get("/api/files")
async def list_files() -> dict[str, Any]:
    return {"workspace": str(WORKSPACE), "children": _tree(WORKSPACE)}


@app.post("/api/folders")
async def create_folder(payload: NewFolder) -> dict[str, str]:
    folder = _workspace_path(payload.path)
    folder.mkdir(parents=True, exist_ok=True)
    return {"path": folder.relative_to(WORKSPACE).as_posix(), "name": folder.name}


@app.post("/api/files/upload")
async def upload_file(folder: str = Form(""), file: UploadFile = File(...)) -> dict[str, str]:
    destination = _workspace_path(folder)
    if not destination.exists() or not destination.is_dir():
        raise HTTPException(status_code=400, detail="Destination folder not found.")
    target = _unique_path(destination, file.filename or "uploaded-file")
    try:
        with target.open("wb") as output:
            shutil.copyfileobj(file.file, output)
    finally:
        await file.close()
    return {"path": target.relative_to(WORKSPACE).as_posix(), "name": target.name}


@app.post("/api/files/move")
async def move_file(payload: MoveFile) -> dict[str, str]:
    source = _workspace_path(payload.source)
    destination = _workspace_path(payload.destination_folder)
    if not source.exists() or source == WORKSPACE:
        raise HTTPException(status_code=404, detail="Source file or folder not found.")
    if not destination.exists() or not destination.is_dir():
        raise HTTPException(status_code=400, detail="Destination folder not found.")
    if source.is_dir() and (destination == source or source in destination.parents):
        raise HTTPException(status_code=400, detail="A folder cannot be moved into itself or one of its subfolders.")
    target = _unique_path(destination, source.name)
    shutil.move(str(source), str(target))
    return {"path": target.relative_to(WORKSPACE).as_posix(), "name": target.name}


@app.post("/api/files/copy")
async def copy_file(payload: MoveFile) -> dict[str, str]:
    source = _workspace_path(payload.source)
    destination = _workspace_path(payload.destination_folder)
    if not source.exists() or source == WORKSPACE:
        raise HTTPException(status_code=404, detail="Source file or folder not found.")
    if not destination.exists() or not destination.is_dir():
        raise HTTPException(status_code=400, detail="Destination folder not found.")
    target = _unique_path(destination, source.name)
    if source.is_dir():
        shutil.copytree(source, target, symlinks=True, ignore=shutil.ignore_patterns(".*", *BLOCKED_PROJECT_DIRS))
    else:
        shutil.copy2(source, target)
    return {"path": target.relative_to(WORKSPACE).as_posix(), "name": target.name}


@app.delete("/api/files")
async def delete_workspace_item(path: str) -> dict[str, str]:
    target = _workspace_path(path)
    if target == WORKSPACE or not target.exists():
        raise HTTPException(status_code=404, detail="File or folder not found.")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"status": "deleted", "path": path}


@app.post("/api/files/rename")
async def rename_file(payload: RenameFile) -> dict[str, str]:
    source = _workspace_path(payload.source)
    new_name = Path(payload.new_name.strip()).name
    if not source.exists() or source == WORKSPACE:
        raise HTTPException(status_code=404, detail="Source file or folder not found.")
    if not new_name or new_name in {".", ".."} or new_name.startswith("."):
        raise HTTPException(status_code=400, detail="Enter a valid name. Names cannot start with a period.")
    target = source.with_name(new_name).resolve()
    if target.parent != source.parent or target == STATE_DIR or STATE_DIR in target.parents:
        raise HTTPException(status_code=400, detail="Items can only be renamed within the workspace.")
    if target.exists() and target != source:
        raise HTTPException(status_code=409, detail="A file or folder with this name already exists.")
    source.rename(target)
    return {"path": target.relative_to(WORKSPACE).as_posix(), "name": target.name}


@app.get("/api/files/text")
async def read_text_file(path: str) -> dict[str, str]:
    file_path = _workspace_path(path)
    if not file_path.is_file() or file_path.suffix.lower() not in TEXT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Preview and context currently support text, source code, JSON, CSV, and YAML files.")
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")[:MAX_CONTEXT_CHARS_PER_FILE]
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {exc}") from exc
    return {"path": path, "content": content}
