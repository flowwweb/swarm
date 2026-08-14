import unittest
from pathlib import Path


class SpecialistTriggerContractTests(unittest.TestCase):
    def test_core_routes_specialist_policy_to_one_hop_hierarchy_contract(self):
        root = Path(__file__).parents[1]
        core = (root / "SKILL.md").read_text(encoding="utf-8")
        hierarchy = (root / "references" / "hierarchy.md").read_text(encoding="utf-8")
        self.assertIn("Load the hierarchy reference for specialist trigger", core)
        self.assertRegex(hierarchy, r"(?is)initial topology.*first mutable handoff")
        self.assertRegex(hierarchy, r"(?is)examples, not an allowlist.*Profession is not singleton")
        self.assertRegex(hierarchy, r"(?is)Task size.*alone do not justify.*stop the next affected mutation")
        self.assertRegex(hierarchy, r"(?is)EXPERT.*bounded uncertainty.*never artifact ownership")


if __name__ == "__main__":
    unittest.main()
