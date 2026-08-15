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
        self.assertIn("never replaces a qualifying visible lane", hierarchy)
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


if __name__ == "__main__":
    unittest.main()
