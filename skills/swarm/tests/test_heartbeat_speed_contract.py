import unittest
from pathlib import Path


class HeartbeatSpeedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (Path(__file__).parents[1] / "SKILL.md").read_text(encoding="utf-8")

    def test_thirty_minute_heartbeat_reaudits_roles_and_requirements(self):
        self.assertIn("When an active durable goal reaches 30 minutes", self.skill)
        self.assertIn("current requirement ledger, role coverage, ownership fit", self.skill)
        self.assertIn("do not preserve initial topology by inertia", self.skill)

    def test_expert_is_bounded_and_critical_path_driven(self):
        self.assertIn("Consider EXPERT whenever one bounded uncertainty", self.skill)
        self.assertIn("without taking artifact ownership", self.skill)
        self.assertIn("Do not create ceremonial experts", self.skill)

    def test_lead_interval_requires_measurable_progress(self):
        self.assertIn("Every mutable LEAD must produce a measurable artifact, proof advance, dependency clearance, or genuinely new exact blocker", self.skill)
        self.assertIn("another narrative update is not progress", self.skill)

    def test_speed_reward_tracks_accepted_proof_not_output(self):
        self.assertIn("best recent time-to-accepted-proof and low correction cost", self.skill)
        self.assertIn("grant fast reliable owners more reuse and autonomy", self.skill)
        self.assertIn("never output volume or speed that weakens quality", self.skill)


if __name__ == "__main__":
    unittest.main()
