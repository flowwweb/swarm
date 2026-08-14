import unittest
from pathlib import Path


class SpecialistTriggerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (Path(__file__).parents[1] / "SKILL.md").read_text(encoding="utf-8")

    def test_cross_cutting_truth_triggers_concrete_specialist_early(self):
        self.assertIn("Materialize a persistent SPECIALIST during initial topology, before the first mutable handoff", self.skill)
        self.assertIn("SPECIALIST is a free role", self.skill)
        self.assertIn("run it before or alongside implementation", self.skill)

    def test_seven_built_in_specialists_are_short_professions(self):
        self.assertIn("The seven built-in examples are ARCHITECT, ENGINEER, DEVELOPER, DESIGNER, RESEARCHER, ANALYST, and STRATEGIST", self.skill)
        self.assertIn("They are examples, not an allowlist: any profession is valid", self.skill)

    def test_professions_are_reusable_concurrently(self):
        self.assertIn("including multiple ARCHITECTs or DEVELOPERs at the same time", self.skill)
        self.assertIn("Profession does not establish singleton ownership", self.skill)

    def test_size_alone_does_not_trigger_specialist(self):
        self.assertIn("Task size, file count, visual variants, or many independent artifacts alone do not justify a SPECIALIST", self.skill)

    def test_late_discovery_stops_next_cross_boundary_mutation(self):
        self.assertIn("stop the next affected mutation, add the missing gate immediately", self.skill)


if __name__ == "__main__":
    unittest.main()
