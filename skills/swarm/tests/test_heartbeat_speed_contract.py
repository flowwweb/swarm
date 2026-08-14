import unittest
from pathlib import Path


class HeartbeatSpeedContractTests(unittest.TestCase):
    def test_core_routes_one_clock_and_recovery_to_monitoring(self):
        root = Path(__file__).parents[1]
        core = (root / "SKILL.md").read_text(encoding="utf-8")
        monitoring = (root / "references" / "monitoring.md").read_text(encoding="utf-8")
        hierarchy = (root / "references" / "hierarchy.md").read_text(encoding="utf-8")
        self.assertIn("Load [monitoring.md]", core)
        self.assertRegex(monitoring, r"(?is)exactly one lightweight wakeup.*CTRL always owns")
        self.assertRegex(monitoring, r"(?is)raw diff, process, test, dependency, and artifact evidence.*does not poll early")
        self.assertRegex(monitoring, r"(?is)no longer than 60 minutes.*miss three.*SUPERVISOR")
        self.assertRegex(hierarchy, r"(?is)request-to-task-ID.*at least five comparable samples.*expected critical-path savings")


if __name__ == "__main__":
    unittest.main()
