"""Tests for layered prompt assembly."""
import unittest

from backend.prompts.prompt_manager import assemble_main_agent_prompt
from backend.context.context_manager import build_session_context


class PromptManagerTests(unittest.TestCase):
    def test_main_agent_prompt_assembles_ordered_layers(self):
        prompt = assemble_main_agent_prompt(
            project_context={"project_root": "/tmp/project", "read_enabled": True, "write_enabled": False},
            session_context=build_session_context(
                conversation_id="chat-test", model="local-model", context_files=["notes.md"]
            ),
        )
        positions = [prompt.index(f"# P{i} —") for i in range(6)]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Team Lead", prompt)
        self.assertIn("not the Product Owner", prompt)
        self.assertIn("Write access: disabled", prompt)
        self.assertIn("Conversation ID: chat-test", prompt)

    def test_main_agent_prompt_contains_runtime_truthfulness_constraints(self):
        prompt = assemble_main_agent_prompt()
        self.assertIn("Never invent or imply the existence of UI buttons", prompt)
        self.assertIn("Never claim that an action was submitted", prompt)
        self.assertIn("Do not fabricate a URL", prompt)

    def test_user_request_layer_is_optional_and_explicit(self):
        prompt = assemble_main_agent_prompt(user_request="Inspect the task plan")
        self.assertIn("# P6 — Current User Request", prompt)
        self.assertIn("Inspect the task plan", prompt)


if __name__ == "__main__":
    unittest.main()
