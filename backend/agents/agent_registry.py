from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..capability_catalog import list_system_capabilities, resolve_agent_tool_permissions


@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    display_name: str
    role_prompt: str
    prompt_path: str
    model: str | None = None
    capabilities: tuple[str, ...] = ()
    allowed_task_types: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    enabled: bool = True
    denied_tools: tuple[str, ...] = ()
    capability_notes: tuple[str, ...] = ()


class AgentRegistry:
    """Loads predefined specialist identities and their owner-managed runtime configuration."""

    def __init__(self, role_directory: Path | None = None, config_path: Path | None = None) -> None:
        self.role_directory = role_directory or Path(__file__).resolve().parents[1] / "prompts" / "roles"
        self.config_path = config_path or Path.home() / "AgentWorkspace" / ".agent_state" / "specialist_agents.json"
        self._agents: dict[str, AgentDefinition] = {}
        self.reload()

    def _read_config(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def reload(self) -> None:
        if not self.role_directory.is_dir():
            raise RuntimeError(f"Agent role directory does not exist: {self.role_directory}")
        config = self._read_config()
        agents: dict[str, AgentDefinition] = {}
        for path in sorted(self.role_directory.glob("*.md")):
            if path.stem == "main_agent":
                continue
            base_prompt = path.read_text(encoding="utf-8").strip()
            if not base_prompt:
                continue
            item = config.get(path.stem, {})
            prompt = str(item.get("role_prompt") or base_prompt).strip()
            heading = next((line.lstrip("# ").strip() for line in base_prompt.splitlines() if line.startswith("# ")), path.stem)
            display_name = str(item.get("display_name") or heading.split(" Role")[0].replace("P2 — ", "").strip())
            agents[path.stem] = AgentDefinition(
                path.stem, display_name, prompt, str(path),
                str(item.get("model") or "").strip() or None,
                tuple(str(v) for v in item.get("capabilities", []) if str(v).strip()),
                tuple(str(v) for v in item.get("allowed_task_types", []) if str(v).strip()),
                tuple(str(v) for v in item.get("allowed_tools", []) if str(v).strip()),
                bool(item.get("enabled", True)),
                tuple(str(v) for v in item.get("denied_tools", []) if str(v).strip()),
                tuple(str(v) for v in item.get("capability_notes", []) if str(v).strip()),
            )
        custom = config.get("__custom_agents__", {})
        if isinstance(custom, dict):
            for agent_id, item in custom.items():
                if not isinstance(item, dict):
                    continue
                prompt = str(item.get("role_prompt") or "").strip()
                if not prompt:
                    continue
                agents[agent_id] = AgentDefinition(
                    agent_id=agent_id,
                    display_name=str(item.get("display_name") or agent_id),
                    role_prompt=prompt,
                    prompt_path="custom",
                    model=str(item.get("model") or "").strip() or None,
                    capabilities=tuple(str(v) for v in item.get("capabilities", []) if str(v).strip()),
                    allowed_task_types=tuple(str(v) for v in item.get("allowed_task_types", []) if str(v).strip()),
                    allowed_tools=tuple(str(v) for v in item.get("allowed_tools", []) if str(v).strip()),
                    enabled=bool(item.get("enabled", True)),
                    denied_tools=tuple(str(v) for v in item.get("denied_tools", []) if str(v).strip()),
                    capability_notes=tuple(str(v) for v in item.get("capability_notes", []) if str(v).strip()),
                )
        self._agents = agents

    def _write_config(self, config: dict[str, Any]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.config_path.with_suffix(".tmp")
        temp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            temp.chmod(0o600)
        except OSError:
            pass
        temp.replace(self.config_path)

    @staticmethod
    def _normalise_agent_payload(payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("display_name") or "").strip()
        role_prompt = str(payload.get("role_prompt") or "").strip()
        model = str(payload.get("model") or "").strip()
        capabilities = payload.get("capabilities", [])
        task_types = payload.get("allowed_task_types", [])
        allowed_tools = payload.get("allowed_tools", [])
        denied_tools = payload.get("denied_tools", [])
        capability_notes = payload.get("capability_notes", [])
        if not name or len(name) > 80:
            raise ValueError("Agent name is required and must be at most 80 characters.")
        if not role_prompt or len(role_prompt) > 30000:
            raise ValueError("Role Instructions are required and must be at most 30,000 characters.")
        if not model:
            raise ValueError("Select an installed model for this Agent.")
        if any(not isinstance(value, list) for value in (capabilities, task_types, allowed_tools, denied_tools, capability_notes)):
            raise ValueError("Capabilities, capability_notes, allowed_task_types, allowed_tools and denied_tools must be lists.")
        return {
            "display_name": name,
            "description": str(payload.get("description") or "").strip()[:500],
            "category": str(payload.get("category") or "Other").strip()[:60],
            "model": model,
            "capabilities": [str(v).strip()[:100] for v in capabilities if str(v).strip()][:30],
            "allowed_task_types": [str(v).strip()[:100] for v in task_types if str(v).strip()][:30],
            "allowed_tools": [str(v).strip()[:100] for v in allowed_tools if str(v).strip()][:100],
            "denied_tools": [str(v).strip()[:100] for v in denied_tools if str(v).strip()][:100],
            "capability_notes": [str(v).strip()[:100] for v in capability_notes if str(v).strip()][:30],
            "enabled": bool(payload.get("enabled", True)),
            "role_prompt": role_prompt,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def save_configuration(self, updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        current = self._read_config()
        valid_ids = {path.stem for path in self.role_directory.glob("*.md") if path.stem != "main_agent"}
        seen: set[str] = set()
        for item in updates:
            agent_id = str(item.get("agent_id", "")).strip().lower()
            if agent_id not in valid_ids:
                raise ValueError(f"Unknown predefined agent: {agent_id}")
            if agent_id in seen:
                raise ValueError(f"Duplicate agent configuration: {agent_id}")
            seen.add(agent_id)
            normalised = self._normalise_agent_payload({
                **item,
                "role_prompt": item.get("role_prompt") or self.get(agent_id).role_prompt,
                "model": item.get("model") or item.get("default_model") or "unconfigured",
            })
            current[agent_id] = normalised
        self._write_config(current)
        self.reload()
        return self.list_agents()

    def create_custom(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self._read_config()
        custom = current.setdefault("__custom_agents__", {})
        if not isinstance(custom, dict):
            custom = {}
            current["__custom_agents__"] = custom
        item = self._normalise_agent_payload(payload)
        agent_id = "agent_" + uuid.uuid4().hex[:12]
        item["created_at"] = datetime.now(timezone.utc).isoformat()
        custom[agent_id] = item
        self._write_config(current)
        self.reload()
        return next(agent for agent in self.list_agents(include_prompt=True) if agent["agent_id"] == agent_id)

    def update_custom(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self._read_config()
        custom = current.get("__custom_agents__", {})
        if not isinstance(custom, dict) or agent_id not in custom:
            raise KeyError("Custom Agent not found.")
        previous = custom[agent_id]
        item = self._normalise_agent_payload(payload)
        item["created_at"] = previous.get("created_at", datetime.now(timezone.utc).isoformat())
        custom[agent_id] = item
        self._write_config(current)
        self.reload()
        return next(agent for agent in self.list_agents(include_prompt=True) if agent["agent_id"] == agent_id)

    def delete_custom(self, agent_id: str) -> None:
        current = self._read_config()
        custom = current.get("__custom_agents__", {})
        if not isinstance(custom, dict) or agent_id not in custom:
            raise KeyError("Custom Agent not found. Predefined Agents cannot be deleted.")
        del custom[agent_id]
        self._write_config(current)
        self.reload()

    def get(self, agent_id: str) -> AgentDefinition | None:
        return self._agents.get(agent_id.strip().lower())

    def list_agents(self, *, include_prompt: bool = False) -> list[dict[str, Any]]:
        result = []
        config = self._read_config()
        capability_names = {item["capability_id"]: item["name"] for item in list_system_capabilities()}
        custom_ids = set(config.get("__custom_agents__", {}).keys()) if isinstance(config.get("__custom_agents__", {}), dict) else set()
        for agent in self._agents.values():
            permissions = resolve_agent_tool_permissions(agent.capabilities, agent.allowed_tools, agent.denied_tools)
            item: dict[str, Any] = {
                "agent_id": agent.agent_id, "display_name": agent.display_name,
                "model": agent.model or "", "capabilities": list(agent.capabilities),
                "allowed_task_types": list(agent.allowed_task_types), "allowed_tools": list(agent.allowed_tools),
                "denied_tools": list(agent.denied_tools), "capability_notes": list(agent.capability_notes),
                "capability_labels": [capability_names.get(value, value) for value in agent.capabilities] + list(agent.capability_notes),
                **permissions, "enabled": agent.enabled,
                "is_custom": agent.agent_id in custom_ids,
                "category": (config.get("__custom_agents__", {}).get(agent.agent_id, {}) if agent.agent_id in custom_ids else config.get(agent.agent_id, {})).get("category", "Other" if agent.agent_id in custom_ids else "Predefined"),
                "description": (config.get("__custom_agents__", {}).get(agent.agent_id, {}) if agent.agent_id in custom_ids else config.get(agent.agent_id, {})).get("description", ""),
            }
            if include_prompt:
                item["role_prompt"] = agent.role_prompt
            result.append(item)
        return result
