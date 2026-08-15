import unittest
from pathlib import Path


class WatchdogContractTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).parents[1]
        self.core = (root / "SKILL.md").read_text(encoding="utf-8")
        self.monitoring = (root / "references" / "monitoring.md").read_text(encoding="utf-8")
        self.hierarchy = (root / "references" / "hierarchy.md").read_text(encoding="utf-8")

    def test_watchdog_is_optional_alert_only_and_has_exactly_three_checks(self):
        self.assertIn("optional CTRL-owned, alert-only scoped sensor", self.core)
        self.assertIn("An unbound goal has no watchdog clock, check, receipt, or alert", self.monitoring)
        self.assertEqual(self.monitoring.count("1. **Progress:**"), 1)
        self.assertEqual(self.monitoring.count("2. **Flow integrity:**"), 1)
        self.assertEqual(self.monitoring.count("3. **Outcome integrity:**"), 1)
        self.assertRegex(self.monitoring, r"`CLEAR`, `ATTENTION`, or `BLOCKER`")
        self.assertRegex(self.monitoring, r"never\nselects or applies a correction")
        self.assertNotIn("SUPERVISOR", self.monitoring)

    def test_alert_route_hears_owner_and_bypasses_only_owner_integrity(self):
        self.assertRegex(self.monitoring, r"Ordinary alerts route first to the watched owner")
        self.assertRegex(self.monitoring, r"owner-integrity alert skips\nthat owner")
        self.assertRegex(self.monitoring, r"watched CTRL requires a named independent REVIEW route ending in\nhuman attention")
        self.assertRegex(self.monitoring, r"Missing, self-referential, cyclic, fabricated, or wrong-scope routes fail closed")

    def test_post_alert_review_is_lean_reversible_and_constraint_aware(self):
        self.assertIn("Owner-heard micro-review", self.monitoring)
        self.assertRegex(self.monitoring, r"asynchronous.*accountable decision owner and watched owner")
        self.assertRegex(self.monitoring, r"same-constraints counterfactual")
        self.assertRegex(self.monitoring, r"single delay, outage, tool/provider failure, or ambiguous alert cannot remove")
        self.assertRegex(self.monitoring, r"smallest reversible response")
        self.assertRegex(self.monitoring, r"repeated comparable evidence or a clear safety")
        self.assertRegex(self.monitoring, r"(?s)temporary containment.*reversal condition")
        self.assertRegex(self.monitoring, r"Do not create a meeting, quorum, committee,\nor recurring status ritual")

    def test_lane_economics_remain_evidence_based(self):
        self.assertRegex(self.hierarchy, r"(?s)request-to-ID.*five comparable samples")
        self.assertRegex(self.hierarchy, r"expected critical-path\nsavings clearly exceed startup")


if __name__ == "__main__":
    unittest.main()
