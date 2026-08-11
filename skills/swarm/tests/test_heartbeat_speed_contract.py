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

    def test_lead_keeps_one_durable_goal_and_optimizes_after_misses(self):
        self.assertIn("Every LEAD creates or continues exactly one durable goal", self.skill)
        self.assertIn("records one measurable next milestone for each 30-minute interval", self.skill)
        self.assertIn("change one constraint, method, dependency, or slice", self.skill)
        self.assertIn("Do not rename, replace, or shrink the goal to erase a miss", self.skill)

    def test_three_consecutive_misses_trigger_supervisor(self):
        self.assertIn("Three consecutive missed milestones under the same durable goal automatically trigger one visible SUPERVISOR", self.skill)
        self.assertIn("A completed milestone resets the consecutive-miss count", self.skill)
        self.assertIn("SUPERVISOR owns progress recovery", self.skill)
        self.assertIn("without taking implementation, architecture, review, topology, or acceptance authority", self.skill)

    def test_speed_reward_tracks_accepted_proof_not_output(self):
        self.assertIn("best recent time-to-accepted-proof and low correction cost", self.skill)
        self.assertIn("grant fast reliable owners more reuse and autonomy", self.skill)
        self.assertIn("never output volume or speed that weakens quality", self.skill)

    def test_visible_task_startup_threshold_uses_observed_host_receipts(self):
        hierarchy = (Path(__file__).parents[1] / "references" / "hierarchy.md").read_text(encoding="utf-8")
        for text in (self.skill, hierarchy):
            self.assertIn("request-to-task-ID", text)
            self.assertIn("task-ID-to-ready", text)
            self.assertIn("ready-to-first-material-artifact-or-proof", text)
            self.assertIn("worktree setup", text)
            self.assertIn("host-reported token usage", text)
            self.assertIn("never estimate missing token usage", text)
            self.assertIn("at least five comparable samples", text)
            self.assertIn("expected critical-path savings exceed", text)
            self.assertIn("keep the slice with its current owner", text)
            self.assertIn("observed cold-start or setup latency plus", text)
            self.assertIn("actual readiness condition", text)
            self.assertIn("A timeout proves only that the chosen window elapsed", text)
            self.assertIn("it does not prove service failure", text)


if __name__ == "__main__":
    unittest.main()
