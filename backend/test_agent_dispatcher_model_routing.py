import unittest
from unittest.mock import AsyncMock

from backend.agents.agent_dispatcher import AgentDispatcher
from backend.agents.agent_registry import AgentDefinition


class FakeRegistry:
    def __init__(self, agent):
        self.agent = agent

    def get(self, agent_id):
        return self.agent if agent_id == self.agent.agent_id else None

    def list_agents(self):
        return []


class AgentDispatcherModelRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatch_uses_agent_assigned_model_not_main_agent_fallback(self):
        agent = AgentDefinition(
            agent_id="developer", display_name="Developer", role_prompt="role",
            prompt_path="test", model="qwen2.5-coder:3b", enabled=True,
        )
        runtime = unittest.mock.Mock()
        runtime.execute = AsyncMock(return_value=type("Result", (), {"as_dict": lambda self: {
            "success": True, "agent_id": "developer", "model": "qwen2.5-coder:3b"
        }})())
        dispatcher = AgentDispatcher(FakeRegistry(agent), runtime)

        result = await dispatcher.dispatch(agent_id="developer", task="Write a function")

        self.assertTrue(result["success"])
        self.assertEqual(runtime.execute.await_args.args[3], "qwen2.5-coder:3b")

    async def test_dispatch_fails_when_agent_has_no_model_instead_of_falling_back(self):
        agent = AgentDefinition(
            agent_id="analyst", display_name="Analyst", role_prompt="role",
            prompt_path="test", model=None, enabled=True,
        )
        runtime = unittest.mock.Mock()
        runtime.execute = AsyncMock()
        dispatcher = AgentDispatcher(FakeRegistry(agent), runtime)

        result = await dispatcher.dispatch(agent_id="analyst", task="Analyse data")

        self.assertFalse(result["success"])
        self.assertIn("No model is configured", result["error"])
        runtime.execute.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
