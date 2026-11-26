import unittest

from backend.main import _proposal_confirmation_payload, _proposal_snapshot_hash


class ProposalConfirmationSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.proposal = {
            "id": "11111111-2222-4333-8444-555555555555",
            "title": "Personal Finance Analytics",
            "objective": "Analyse personal spending.",
            "scope": {"features": ["Import", "Dashboard"]},
            "deliverables": ["Web application"],
            "milestones": ["MVP"],
            "tasks": [],
            "agent_allocations": [],
            "timeline": {"duration": "12 weeks"},
            "risks": ["Bank API compatibility"],
            "assumptions": ["User provides transaction data"],
            "priority": "medium",
            "baseline_due_date": None,
            "updated_at": "2026-11-24T03:31:14+00:00",
            "status": "discussion",
        }

    def test_confirmation_card_uses_persisted_proposal_fields(self):
        card = _proposal_confirmation_payload(self.proposal)
        self.assertEqual(card["proposal_id"], self.proposal["id"])
        self.assertEqual(card["title"], self.proposal["title"])
        self.assertEqual(card["scope"], self.proposal["scope"])
        self.assertEqual(card["snapshot_hash"], _proposal_snapshot_hash(self.proposal))

    def test_snapshot_hash_changes_when_reviewed_content_changes(self):
        original_hash = _proposal_snapshot_hash(self.proposal)
        changed = dict(self.proposal)
        changed["scope"] = {"features": ["Import", "Dashboard", "Forecasting"]}
        self.assertNotEqual(original_hash, _proposal_snapshot_hash(changed))

    def test_snapshot_hash_changes_when_proposal_revision_timestamp_changes(self):
        original_hash = _proposal_snapshot_hash(self.proposal)
        changed = dict(self.proposal)
        changed["updated_at"] = "2026-11-24T04:00:00+00:00"
        self.assertNotEqual(original_hash, _proposal_snapshot_hash(changed))


if __name__ == "__main__":
    unittest.main()
