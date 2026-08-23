from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RoutingContractTests(unittest.TestCase):
    def test_visible_lane_is_not_replaced_by_subagent(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        hierarchy = (ROOT / "references" / "hierarchy.md").read_text(encoding="utf-8")
        self.assertIn("Materialize a visible task lane", skill)
        self.assertIn("Use a subagent only as short bounded capacity", skill)
        self.assertIn("interruption-safe resumption", hierarchy)
        self.assertRegex(
            hierarchy,
            r"(?:never replaces a qualifying visible lane|never replaces a warranted LEAD or\s+DOER)",
        )
        self.assertIn("Do not disguise a subagent as durable ownership", hierarchy)

    def test_user_model_and_reasoning_are_never_silently_overridden(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        providers = (ROOT / "references" / "model-providers.md").read_text(encoding="utf-8")
        for text in (skill, providers):
            self.assertIn("explicit user", text)
            self.assertIn("reasoning level", text)
            self.assertIn("exact blocker", text)
        self.assertIn("never applies one unless the user explicitly asks", skill)
        self.assertIn("must not silently lower, raise, replace, or reinterpret", providers)

    def test_recursive_lead_and_leaf_subagent_contract_is_explicit(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        hierarchy = (ROOT / "references" / "hierarchy.md").read_text(encoding="utf-8")
        task = (ROOT / "references" / "task-contract.md").read_text(encoding="utf-8")
        combined = "\n".join((skill, hierarchy, task))
        self.assertRegex(
            combined,
            r"Structural authority is exactly `CTRL`, `LEAD`, and\s+`DOER`",
        )
        self.assertRegex(combined, r"(?:a )?LEAD may produce directly")
        self.assertIn("nested LEAD", combined)
        self.assertIn("may_need_recruitment", combined)
        self.assertIn("requires_recursive_delegation", combined)
        self.assertIn("PROMOTE_TO_VISIBLE_TASK", combined)
        self.assertIn("non-recursive leaf", combined)

    def test_recruitment_and_independent_review_are_evidence_bound(self) -> None:
        hierarchy = (ROOT / "references" / "hierarchy.md").read_text(encoding="utf-8")
        task = (ROOT / "references" / "task-contract.md").read_text(encoding="utf-8")
        combined = "\n".join((hierarchy, task))
        self.assertIn("efficiency.doer_wip_limit", combined)
        self.assertIn("Delegated active", combined)
        self.assertIn("Blocked work", combined)
        self.assertIn("typed material-receipt/forecast", combined)
        self.assertRegex(combined, r"separate\s+visible owner from the producer")
        self.assertRegex(combined, r"not a fourth\s+structural authority")


if __name__ == "__main__":
    unittest.main()
