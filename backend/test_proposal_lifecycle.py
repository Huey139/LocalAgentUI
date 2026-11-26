from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from . import database, project_prompts, team_orchestration_api
from .database import connect, initialize_database
from . import proposal_api
from .main import _active_discussion_proposal_id, _is_explicit_natural_formal_approval
from .proposal_api import (
    LifecycleComment,
    ProposalCreate,
    ProposalUpdate,
    create_proposal,
    formally_approve_proposal,
    update_proposal,
)


class ProposalLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.original_db_path = database.DB_PATH
        self.original_prompt_root = project_prompts.PROMPT_ROOT
        self.original_plans_path = team_orchestration_api.PLANS
        self.original_proposal_plans_path = proposal_api.PLANS
        database.DB_PATH = root / "test.db"
        project_prompts.PROMPT_ROOT = root / "project_prompts"
        team_orchestration_api.PLANS = root / "project_team_plans.json"
        proposal_api.PLANS = root / "project_team_plans.json"
        initialize_database()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        project_prompts.PROMPT_ROOT = self.original_prompt_root
        team_orchestration_api.PLANS = self.original_plans_path
        proposal_api.PLANS = self.original_proposal_plans_path
        self.temp_dir.cleanup()

    def _proposal(self):
        return create_proposal(ProposalCreate(
            title="Lifecycle Test Project",
            objective="Verify proposal to formal project creation.",
            scope={"in_scope": ["proposal discussion", "team planning"]},
            deliverables=["Approved project record"],
            tasks=[{"name": "This remains proposal-only until the next release"}],
        ))

    def _attach_valid_team_plan(self, proposal_id: str):
        with connect() as conn:
            row = conn.execute(
                "SELECT agent_allocations_json FROM sys_project_proposals WHERE id=?",
                (proposal_id,),
            ).fetchone()
            allocations = json.loads(row["agent_allocations_json"] or "{}")
            if not isinstance(allocations, dict):
                allocations = {"legacy_allocations": allocations}
            allocations["team_plan"] = {
                "status": "draft",
                "workstreams": [{"name": "Quality Assurance"}],
                "proposed_team": [{"agent_id": "qa_agent", "status": "ready"}],
                "capability_gaps": [],
            }
            conn.execute(
                "UPDATE sys_project_proposals SET agent_allocations_json=? WHERE id=?",
                (json.dumps(allocations), proposal_id),
            )


    def test_natural_language_formal_approval_requires_affirmative_instruction(self):
        self.assertTrue(_is_explicit_natural_formal_approval("确认正式立项"))
        self.assertTrue(_is_explicit_natural_formal_approval("请批准立项"))
        self.assertTrue(_is_explicit_natural_formal_approval("Formally approve the project"))
        self.assertFalse(_is_explicit_natural_formal_approval("怎么正式立项？"))
        self.assertFalse(_is_explicit_natural_formal_approval("先不要正式立项"))
        self.assertFalse(_is_explicit_natural_formal_approval("我不确定是否正式立项"))
        self.assertFalse(_is_explicit_natural_formal_approval("Submit the proposal for approval"))
        self.assertFalse(_is_explicit_natural_formal_approval("正式立项需要多少预算？"))

    def test_saved_discussion_proposal_is_detected_in_followup_chat(self):
        proposal = self._proposal()
        chat = {"messages": [{"role": "assistant", "content": f"## Proposal\n\n**Proposal ID:** {proposal['id']}\n"}]}
        self.assertEqual(_active_discussion_proposal_id(chat), proposal["id"])

    def test_proposal_is_saved_as_discussion_draft_and_can_be_revised(self):
        proposal = self._proposal()
        self.assertEqual(proposal["status"], "discussion")
        self.assertIsNotNone(proposal["id"])
        revised = update_proposal(
            proposal["id"], ProposalUpdate(objective="Revised objective."),
        )
        self.assertEqual(revised["objective"], "Revised objective.")
        self.assertEqual(revised["status"], "discussion")

    def test_formal_creation_does_not_require_or_implicitly_approve_team_plan(self):
        proposal = self._proposal()
        result = formally_approve_proposal(proposal["id"], LifecycleComment(comment="Confirm"))
        project_id = result["project"]["id"]
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(result["tasks_created"], 0)
        self.assertEqual(result["assignments_created"], 0)
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sys_projects WHERE id=?", (project_id,)).fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sys_tasks WHERE project_id=?", (project_id,)).fetchone()[0], 0)
            approved = json.loads(conn.execute("SELECT approved_baseline_json FROM sys_project_proposals WHERE id=?", (proposal["id"],)).fetchone()[0])
            self.assertNotIn("team_plan", approved["agent_allocations_json"])
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM sys_task_assignments a JOIN sys_tasks t ON t.id=a.task_id WHERE t.project_id=?",
                (project_id,),
            ).fetchone()[0], 0)
        with self.assertRaises(HTTPException) as no_plan:
            team_orchestration_api.get_team_plan(project_id)
        self.assertEqual(no_plan.exception.status_code, 404)

    def test_existing_team_plan_is_linked_but_not_implicitly_approved_on_formal_creation(self):
        proposal = self._proposal()
        self._attach_valid_team_plan(proposal["id"])
        result = formally_approve_proposal(proposal["id"], LifecycleComment(comment="Project only approval"))
        project_id = result["project"]["id"]
        with connect() as conn:
            plan_row = conn.execute("SELECT project_id, status FROM sys_team_plans WHERE proposal_id=?", (proposal["id"],)).fetchone()
            self.assertEqual(plan_row["project_id"], project_id)
            self.assertEqual(plan_row["status"], "draft")

    def test_formal_creation_is_idempotent_and_locks_proposal(self):
        proposal = self._proposal()
        first = formally_approve_proposal(proposal["id"], LifecycleComment())
        second = formally_approve_proposal(proposal["id"], LifecycleComment())
        self.assertEqual(first["project"]["id"], second["project"]["id"])
        with self.assertRaises(HTTPException) as locked:
            update_proposal(proposal["id"], ProposalUpdate(objective="Must not change"))
        self.assertEqual(locked.exception.status_code, 409)

    def test_team_plan_can_be_approved_after_formal_project_creation(self):
        proposal = self._proposal()
        self._attach_valid_team_plan(proposal["id"])
        result = formally_approve_proposal(proposal["id"], LifecycleComment(comment="Approve project independently"))
        approved = team_orchestration_api.approve_proposal_team_plan(proposal["id"])
        self.assertEqual(approved["status"], "owner_approved")
        self.assertEqual(approved["project_id"], result["project"]["id"])
        project_plan = team_orchestration_api.get_team_plan(result["project"]["id"])
        self.assertEqual(project_plan["status"], "owner_approved")

    def test_proposal_revision_invalidates_previous_team_plan(self):
        proposal = self._proposal()
        self._attach_valid_team_plan(proposal["id"])
        update_proposal(proposal["id"], ProposalUpdate(objective="Changed after team planning."))
        with connect() as conn:
            allocations = json.loads(conn.execute(
                "SELECT agent_allocations_json FROM sys_project_proposals WHERE id=?",
                (proposal["id"],),
            ).fetchone()[0])
        self.assertEqual(allocations["team_plan"]["status"], "stale")
        result = formally_approve_proposal(proposal["id"], LifecycleComment(comment="Project approval is independent of stale staffing plan"))
        self.assertTrue(result["project"]["id"])
        self.assertEqual(result["team_plan_status"], "stale")


if __name__ == "__main__":
    unittest.main()
