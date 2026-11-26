from __future__ import annotations

import ipaddress
import json
import os
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


class ToolRegistry:
    """Persistent registry for owner-configured HTTP API tools.

    Secrets are never stored here. A tool may reference an environment variable
    name; the value is resolved only inside the backend executor.
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or Path.home() / "AgentWorkspace" / ".agent_state" / "tools.json"
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> list[dict[str, Any]]:
        try:
            value = json.loads(self.config_path.read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _write(self, items: list[dict[str, Any]]) -> None:
        temp = self.config_path.with_suffix(".tmp")
        temp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        temp.replace(self.config_path)

    @staticmethod
    def _validate_endpoint(endpoint: str) -> str:
        parsed = urlparse(endpoint.strip())
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("API endpoint must be an HTTPS URL without embedded credentials, query strings or fragments. Pass request values as tool parameters.")
        host = parsed.hostname.lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError("Local and internal hostnames are not allowed for configurable API tools.")
        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            try:
                addresses = [ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)]
            except OSError as exc:
                raise ValueError("API hostname could not be resolved.") from exc
        if not addresses or any(not address.is_global for address in addresses):
            raise ValueError("API endpoint must resolve only to public IP addresses.")
        return endpoint.strip()

    @staticmethod
    def _validate(item: dict[str, Any]) -> dict[str, Any]:
        name = str(item.get("name", "")).strip()
        description = str(item.get("description", "")).strip()
        category = str(item.get("category", "other")).strip().lower()
        endpoint = ToolRegistry._validate_endpoint(str(item.get("endpoint", "")))
        method = str(item.get("method", "GET")).upper()
        if not name or len(name) > 80 or not description or len(description) > 500:
            raise ValueError("Tool name and description are required (maximum 80 and 500 characters).")
        if method not in {"GET", "POST"}:
            raise ValueError("Only GET and POST methods are supported.")
        if category not in {"search", "database", "file", "code", "api", "other"}:
            raise ValueError("Unsupported tool category.")
        function_name = str(item.get("function_name") or "").strip()
        if not function_name:
            function_name = "api_" + uuid.uuid4().hex[:12]
        if not function_name.replace("_", "").isalnum() or len(function_name) > 64:
            raise ValueError("Invalid tool function name.")
        properties = item.get("parameters", {})
        if not isinstance(properties, dict) or len(properties) > 30:
            raise ValueError("Parameters must be a JSON object with at most 30 fields.")
        required = item.get("required", [])
        if not isinstance(required, list) or any(key not in properties for key in required):
            raise ValueError("Required parameters must reference defined parameter names.")
        for key, definition in properties.items():
            if not isinstance(key, str) or not key.replace("_", "").isalnum() or not isinstance(definition, dict):
                raise ValueError("Each parameter needs a simple name and a definition.")
            if definition.get("type", "string") not in {"string", "number", "integer", "boolean"}:
                raise ValueError("Only string, number, integer and boolean parameters are supported.")
        auth_env = str(item.get("credential_env") or "").strip()
        if auth_env and (not auth_env.replace("_", "").isalnum() or auth_env.upper() != auth_env):
            raise ValueError("Credential reference must be an uppercase environment variable name.")
        return {
            "name": name, "description": description, "category": category,
            "endpoint": endpoint, "method": method, "function_name": function_name,
            "parameters": properties, "required": required, "credential_env": auth_env,
        }

    def list_tools(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._read()]

    def get(self, tool_id: str) -> dict[str, Any] | None:
        return next((dict(item) for item in self._read() if item.get("tool_id") == tool_id), None)

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        item = self._validate(payload)
        items = self._read()
        if any(existing["function_name"] == item["function_name"] for existing in items):
            raise ValueError("A tool with this function name already exists.")
        now = datetime.now(timezone.utc).isoformat()
        item.update(tool_id=f"tool_{uuid.uuid4().hex[:12]}", enabled=False, created_at=now, updated_at=now, version=1, implementation_type="api")
        items.append(item)
        self._write(items)
        return dict(item)

    def update(self, tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        items = self._read()
        index = next((i for i, item in enumerate(items) if item.get("tool_id") == tool_id), None)
        if index is None:
            raise KeyError("Tool not found.")
        update_payload = dict(payload)
        existing = items[index]
        update_payload.setdefault("function_name", existing.get("function_name"))
        item = self._validate(update_payload)
        if any(other.get("function_name") == item["function_name"] and other.get("tool_id") != tool_id for other in items):
            raise ValueError("A tool with this function name already exists.")
        old = items[index]
        item.update(tool_id=tool_id, enabled=bool(old.get("enabled", False)), created_at=old["created_at"], updated_at=datetime.now(timezone.utc).isoformat(), version=int(old.get("version", 1)) + 1, implementation_type="api")
        items[index] = item
        self._write(items)
        return dict(item)

    def set_enabled(self, tool_id: str, enabled: bool) -> dict[str, Any]:
        items = self._read()
        item = next((entry for entry in items if entry.get("tool_id") == tool_id), None)
        if item is None:
            raise KeyError("Tool not found.")
        item["enabled"] = bool(enabled)
        item["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write(items)
        return dict(item)

    def delete(self, tool_id: str) -> None:
        items = self._read()
        remaining = [item for item in items if item.get("tool_id") != tool_id]
        if len(remaining) == len(items):
            raise KeyError("Tool not found.")
        self._write(remaining)

    async def execute(self, item: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
        if not item.get("enabled"):
            raise PermissionError("This tool is disabled.")
        unknown = set(arguments) - set(item.get("parameters", {}))
        missing = set(item.get("required", [])) - set(arguments)
        if unknown or missing:
            raise ValueError(f"Invalid arguments. Unknown: {sorted(unknown)}; missing: {sorted(missing)}")
        endpoint = self._validate_endpoint(item["endpoint"])
        headers: dict[str, str] = {"Accept": "application/json"}
        env_name = item.get("credential_env")
        if env_name:
            secret = os.getenv(env_name, "")
            if not secret:
                raise RuntimeError(f"Credential '{env_name}' is not configured in the environment.")
            headers["Authorization"] = f"Bearer {secret}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0), follow_redirects=False, trust_env=False) as client:
            if item["method"] == "GET":
                response = await client.get(endpoint, params=arguments, headers=headers)
            else:
                response = await client.post(endpoint, json=arguments, headers=headers)
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ValueError("API response exceeded the 1 MB limit.")
            try:
                data = response.json()
            except ValueError:
                data = {"text": response.text[:20000]}
            return {"status_code": response.status_code, "data": data}
