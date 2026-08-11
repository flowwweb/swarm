import unittest
from pathlib import Path


class HeartbeatSpeedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (Path(__file__).parents[1] / "SKILL.md").read_text(encoding="utf-8")

    def test_event_driven_watchdog_has_one_clock(self):
        self.assertIn("exactly one watchdog owns the clock", self.skill)
        self.assertIn("CTRL always owns it", self.skill)
        self.assertIn("including its own", self.skill)
        self.assertIn("schedules exactly one lightweight wakeup", self.skill)
        self.assertIn("fallback integrity audit for a lost or missing scheduled wakeup", self.skill)

    def test_expert_is_bounded_and_critical_path_driven(self):
        self.assertIn("Consider EXPERT whenever one bounded uncertainty", self.skill)
        self.assertIn("without taking artifact ownership", self.skill)
        self.assertIn("Do not create ceremonial experts", self.skill)

    def test_due_review_requires_raw_evidence(self):
        self.assertIn("raw diff, process, tests, dependencies, and artifacts", self.skill)
        self.assertIn("Activity-only updates are rejected", self.skill)

    def test_lead_keeps_one_durable_goal_and_optimizes_after_misses(self):
        self.assertIn("Every active durable goal keeps one stable identity", self.skill)
        self.assertIn("locally chosen review horizon no longer than 60 minutes", self.skill)
        self.assertIn("Do not rename, reset, replace, or shrink it to erase a miss", self.skill)

    def test_three_consecutive_misses_trigger_supervisor(self):
        self.assertIn("miss three triggers one SUPERVISOR", self.skill)
        self.assertIn("completed milestone resets only the consecutive-miss count", self.skill)
        self.assertIn("SUPERVISOR owns progress recovery", self.skill)
        self.assertIn("without taking implementation, specialist, review, topology, or acceptance authority", self.skill)

    def test_speed_reward_tracks_accepted_proof_not_output(self):
        self.assertIn("best recent time-to-accepted-proof and low correction cost", self.skill)
        self.assertIn("preserving proof and authority", self.skill)

    def test_visible_task_startup_threshold_uses_observed_host_receipts(self):
        hierarchy = (Path(__file__).parents[1] / "references" / "hierarchy.md").read_text(encoding="utf-8")
        for text in (self.skill, hierarchy):
            self.assertIn("request-to-task-ID", text)
            self.assertIn("task-ID-to-ready", text)
            self.assertIn("ready-to-first-material-artifact-or-proof", text)
            self.assertIn("worktree setup", text)
            self.assertIn("host-reported token usage", text)
            self.assertIn("never estimate missing token usage", " ".join(text.split()))
            self.assertIn("at least five comparable samples", text)
            self.assertIn("expected critical-path savings exceed", text)
            self.assertIn("keep the slice with its current owner", text)
            self.assertIn("observed cold-start or setup latency plus", text)
            self.assertIn("actual readiness condition", text)
            self.assertIn("A timeout proves only that the chosen window elapsed", text)
            self.assertIn("it does not prove service failure", text)


if __name__ == "__main__":
    unittest.main()
