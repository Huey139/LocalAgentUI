from __future__ import annotations

import copy
import json
import inspect
from dataclasses import dataclass
from typing import Any, Callable

ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ToolEntry:
    """A registered tool's immutable handler reference and private schema copy."""

    schema: dict[str, Any]
    handler: ToolHandler


class ToolManager:
    """Tool registry and the single serialization boundary for tool results.

    Handlers MUST return Python dictionaries. ToolManager wraps each handler
    result exactly once and serializes the outer response exactly once.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}

    def register_schema(self, schema: dict[str, Any], handler: ToolHandler) -> None:
        if not isinstance(schema, dict):
            raise TypeError("Tool schema must be a dictionary.")
        function = schema.get("function")
        if not isinstance(function, dict):
            raise ValueError("Tool schema must contain a function object.")
        name = function.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Tool schema must contain a non-empty function.name.")
        if not callable(handler):
            raise TypeError(f"Handler for '{name}' must be callable.")
        if not isinstance(function.get("parameters"), dict):
            raise ValueError(f"Tool schema for '{name}' must define parameters as an object.")
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered.")
        self._tools[name] = ToolEntry(copy.deepcopy(schema), handler)

    def register(
        self, name: str, description: str, parameters: dict[str, Any], handler: ToolHandler
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Tool name must be a non-empty string.")
        if not isinstance(description, str):
            raise TypeError("Tool description must be a string.")
        if not isinstance(parameters, dict):
            raise TypeError("Tool parameters must be a JSON-schema object.")
        self.register_schema({
            "type": "function",
            "function": {
                "name": name.strip(),
                "description": description,
                "parameters": parameters,
            },
        }, handler)

    def schemas(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(entry.schema) for entry in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    @staticmethod
    def _error_detail(exc: Exception) -> str:
        detail = getattr(exc, "detail", None)
        return str(detail if detail is not None else (str(exc) or type(exc).__name__))

    def execute_result(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        entry = self._tools.get(name)
        if entry is None:
            return {"success": False, "tool": name, "error_type": "ToolNotFound",
                    "error": f"Tool '{name}' is not registered."}
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return {"success": False, "tool": name, "error_type": "InvalidArguments",
                    "error": "Arguments must be a JSON object."}
        try:
            result = entry.handler(copy.deepcopy(arguments))
            if not isinstance(result, dict):
                raise TypeError(
                    f"Tool handler '{name}' must return dict, got {type(result).__name__}."
                )
            return {"success": True, "tool": name, "result": result}
        except Exception as exc:
            return {"success": False, "tool": name, "error_type": type(exc).__name__,
                    "error": self._error_detail(exc)}

    async def execute_async_result(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        entry = self._tools.get(name)
        if entry is None:
            return {"success": False, "tool": name, "error_type": "ToolNotFound", "error": f"Tool '{name}' is not registered."}
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return {"success": False, "tool": name, "error_type": "InvalidArguments", "error": "Arguments must be a JSON object."}
        try:
            result = entry.handler(copy.deepcopy(arguments))
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, dict):
                raise TypeError(f"Tool handler '{name}' must return dict, got {type(result).__name__}.")
            return {"success": True, "tool": name, "result": result}
        except Exception as exc:
            return {"success": False, "tool": name, "error_type": type(exc).__name__, "error": self._error_detail(exc)}

    async def execute_async(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        return json.dumps(await self.execute_async_result(name, arguments), ensure_ascii=False, default=str)

    def execute(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        """Synchronous execution for synchronous built-in tools."""
        return json.dumps(self.execute_result(name, arguments), ensure_ascii=False, default=str)
