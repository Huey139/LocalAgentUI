from __future__ import annotations

from typing import Any

from .agent_registry import AgentRegistry
from .agent_runtime import AgentRuntime
from .agent_result_manager import AgentResultManager


class AgentDispatcher:
    """Validates dispatch metadata and routes work through the canonical P0-P6 runtime."""

    def __init__(self, registry: AgentRegistry, runtime: AgentRuntime,
                 result_manager: AgentResultManager | None = None) -> None:
        self.registry = registry
        self.runtime = runtime
        self.result_manager = result_manager or AgentResultManager()

    async def dispatch(
        self,
        *,
        agent_id: str,
        task: str,
        context: str = "",
        project_id: str | None = None,
        conversation_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(task, str) or not task.strip():
            return {"success": False, "error": "A non-empty task description is required."}
        agent = self.registry.get(agent_id)
        if agent is None:
            return {
                "success": False,
                "error": f"Unknown specialist agent '{agent_id}'.",
                "available_agents": self.registry.list_agents(),
            }
        if not agent.enabled:
            return {"success": False, "agent_id": agent.agent_id, "error": "This Specialist Agent is disabled in Agent Management."}
        selected_model = agent.model
        if not selected_model:
            return {"success": False, "agent_id": agent.agent_id, "error": "No model is configured for this Specialist Agent."}
        result = await self.runtime.execute(
            agent, task, context, selected_model,
            project_id=project_id,
            conversation_id=conversation_id,
            task_id=task_id,
        )
        return self.result_manager.record(result.as_dict())
