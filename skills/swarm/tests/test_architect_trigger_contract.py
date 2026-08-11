import unittest
from pathlib import Path


class ArchitectTriggerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (Path(__file__).parents[1] / "SKILL.md").read_text(encoding="utf-8")

    def test_coupled_system_boundaries_trigger_architect_early(self):
        self.assertIn("Materialize ARCHITECT during initial topology, before the first mutable handoff", self.skill)
        self.assertIn("shared authority, lifecycle, contracts, or integration", self.skill)
        self.assertIn("run it before or alongside implementation", self.skill)

    def test_size_alone_does_not_trigger_architect(self):
        self.assertIn("Task size, file count, visual variants, or many independent artifacts alone do not justify ARCHITECT", self.skill)

    def test_late_discovery_stops_next_cross_boundary_mutation(self):
        self.assertIn("stop the next cross-boundary mutation, add the missing gate immediately", self.skill)


if __name__ == "__main__":
    unittest.main()
