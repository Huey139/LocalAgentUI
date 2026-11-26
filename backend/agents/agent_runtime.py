from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ..prompts.prompt_manager import assemble_runtime_prompt
from ..context.context_manager import build_session_context, build_task_context
from ..context.runtime_environment import build_runtime_environment
from ..tools.tool_manager import ToolManager
from ..tools.sqlite_operations import register_sqlite_operation_tools
from ..tools.tool_registry import ToolRegistry
from ..tools.file_management_tools import WorkspaceFileManager, register_file_tools
from ..capability_catalog import resolve_agent_tool_permissions
from .agent_registry import AgentDefinition


@dataclass
class AgentExecutionResult:
    success: bool
    agent_id: str
    content: str = ""
    model: str = ""
    error: str | None = None
    project_id: str | None = None
    task_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "agent_id": self.agent_id,
            "content": self.content,
            "model": self.model,
            "error": self.error,
            "project_id": self.project_id,
            "task_id": self.task_id,
        }


class AgentRuntime:
    """Executes a Specialist with bounded tool access and the shared P0-P6 prompt builder."""

    def __init__(self, base_url: str, default_model: str, timeout_seconds: float = 180.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds

    def _tool_manager(self, agent: AgentDefinition) -> ToolManager:
        manager = ToolManager()
        permissions = resolve_agent_tool_permissions(agent.capabilities, agent.allowed_tools, agent.denied_tools)
        effective_tools = set(permissions["effective_tools"])
        # Read-only access remains a platform default. Mutating tools are granted
        # only by an assigned Capability or an explicit direct Tool permission.
        denied_tools = set(agent.denied_tools)
        register_sqlite_operation_tools(
            manager,
            allow_modify="sqlite_modify" in effective_tools,
            allow_query="sqlite_query" not in denied_tools,
        )

        workspace = Path(os.getenv("AGENT_WORKSPACE", str(Path.home() / "AgentWorkspace"))).expanduser().resolve()
        state_dir = workspace / ".agent_state"
        settings_path = state_dir / "project_permissions.json"
        project_root = Path(__file__).resolve().parents[2]
        read_enabled, write_enabled = True, True
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            project_root = Path(settings.get("project_root") or project_root).expanduser().resolve()
            read_enabled = bool(settings.get("read_enabled", True))
            write_enabled = bool(settings.get("write_enabled", True)) and read_enabled
        except (OSError, json.JSONDecodeError, TypeError):
            pass
        if read_enabled:
            file_manager = WorkspaceFileManager(project_root, state_dir)
            allow_file_write = write_enabled and "workspace_modify" in effective_tools
            allow_file_read = not ({"workspace_list", "workspace_read"} & denied_tools)
            register_file_tools(manager, file_manager, allow_write=allow_file_write, allow_read=allow_file_read, allow_delete=False)

        registry = ToolRegistry(state_dir / "tools.json")
        allowed = effective_tools
        for item in registry.list_tools():
            if not item.get("enabled") or item.get("function_name") not in allowed:
                continue
            schema = {
                "type": "function",
                "function": {
                    "name": item["function_name"],
                    "description": item["description"],
                    "parameters": {
                        "type": "object",
                        "properties": item.get("parameters", {}),
                        "required": item.get("required", []),
                        "additionalProperties": False,
                    },
                },
            }
            async def handler(args: dict[str, Any], tool=item, tool_registry=registry):
                return await tool_registry.execute(tool, args)
            manager.register_schema(schema, handler)
        return manager

    @staticmethod
    def _parse_arguments(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                value = json.loads(raw)
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    async def execute(
        self,
        agent: AgentDefinition,
        task: str,
        context: str = "",
        model: str | None = None,
        *,
        project_id: str | None = None,
        conversation_id: str | None = None,
        task_id: str | None = None,
    ) -> AgentExecutionResult:
        selected_model = model or self.default_model
        try:
            tool_manager = self._tool_manager(agent)
            workspace = Path(os.getenv("AGENT_WORKSPACE", str(Path.home() / "AgentWorkspace"))).expanduser().resolve()
            state_dir = workspace / ".agent_state"
            settings_path = state_dir / "project_permissions.json"
            authorised_root = Path(__file__).resolve().parents[2]
            read_enabled, write_enabled = True, True
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
                authorised_root = Path(settings.get("project_root") or authorised_root).expanduser().resolve()
                read_enabled = bool(settings.get("read_enabled", True))
                write_enabled = bool(settings.get("write_enabled", True)) and read_enabled
            except (OSError, json.JSONDecodeError, TypeError):
                pass
            runtime_environment = build_runtime_environment(
                agent_id=agent.agent_id,
                model=selected_model,
                available_tools=tool_manager.names(),
                allowed_tools=tool_manager.names(),
                workspace_root=workspace,
                project_root=authorised_root,
                read_enabled=read_enabled,
                write_enabled=write_enabled and "workspace_modify" in effective_tools,
                ollama_base_url=self.base_url,
            )
            system_prompt = assemble_runtime_prompt(
                agent_id=agent.agent_id,
                agent_role_prompt=agent.role_prompt,
                project_id=project_id,
                session_context=build_session_context(
                    conversation_id=conversation_id or "specialist-dispatch",
                    session_id=conversation_id or "specialist-dispatch",
                    project_id=project_id,
                    model=selected_model,
                ),
                runtime_environment=runtime_environment,
                task_context=build_task_context(
                    task_id=task_id,
                    task_description="",
                    supplied_context=context,
                ),
                current_instruction=None,
            )
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "# P6 — Main Agent Task Instruction\n" + task.strip()},
            ]
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds, connect=10.0)) as client:
                for _ in range(6):
                    body: dict[str, Any] = {"model": selected_model, "messages": messages, "stream": False}
                    schemas = tool_manager.schemas()
                    if schemas:
                        body["tools"] = schemas
                        body["tool_choice"] = "auto"
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": "Bearer ollama"},
                        json=body,
                    )
                    response.raise_for_status()
                    payload = response.json()
                    choices = payload.get("choices") if isinstance(payload, dict) else None
                    message = choices[0].get("message", {}) if isinstance(choices, list) and choices else {}
                    if not isinstance(message, dict):
                        raise ValueError("Specialist model returned an invalid message.")
                    calls = message.get("tool_calls") or []
                    if not calls:
                        content = message.get("content")
                        if not isinstance(content, str) or not content.strip():
                            return AgentExecutionResult(False, agent.agent_id, model=selected_model, error="Specialist model returned an empty response.", project_id=project_id, task_id=task_id)
                        return AgentExecutionResult(True, agent.agent_id, content.strip(), selected_model, project_id=project_id, task_id=task_id)
                    messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": calls})
                    for call in calls:
                        function = call.get("function", {}) if isinstance(call, dict) else {}
                        name = function.get("name", "")
                        arguments = self._parse_arguments(function.get("arguments", {}))
                        result = await tool_manager.execute_async(name, arguments)
                        messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})
                return AgentExecutionResult(False, agent.agent_id, model=selected_model, error="Specialist reached the six-step tool-call limit without a final answer.", project_id=project_id, task_id=task_id)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, RuntimeError, OSError) as exc:
            return AgentExecutionResult(
                False, agent.agent_id, model=selected_model,
                error=f"{type(exc).__name__}: {exc}",
                project_id=project_id, task_id=task_id,
            )
