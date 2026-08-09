from __future__ import annotations

import json
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SKILL = SKILL_ROOT / "SKILL.md"
EVALS = SKILL_ROOT / "evals" / "evals.json"


class RushSkillStructureTests(unittest.TestCase):
    def test_core_skill_stays_below_500_lines(self) -> None:
        self.assertLess(len(SKILL.read_text(encoding="utf-8").splitlines()), 500)

    def test_eval_fixtures_are_structurally_valid(self) -> None:
        payload = json.loads(EVALS.read_text(encoding="utf-8"))
        evals = payload["evals"]
        ids = [item["id"] for item in evals]
        self.assertEqual(ids, list(range(1, len(evals) + 1)))
        self.assertEqual(
            sum("RUSH-FB-20260809-WINPY-01" in item["prompt"] for item in evals),
            1,
        )

        referenced = []
        for item in evals:
            self.assertTrue(item["prompt"])
            self.assertTrue(item["expected_output"])
            self.assertTrue(item["assertions"])
            for relative in item["files"]:
                path = SKILL_ROOT / relative
                self.assertTrue(path.is_file(), relative)
                fixture = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn(fixture.get("fixture_kind"), {"runtime_recovery", "hierarchy_routing"})
                self.assertTrue(fixture.get("case"))
                referenced.append(path.resolve())

        fixture_root = SKILL_ROOT / "evals" / "fixtures"
        fixtures = sorted(path.resolve() for path in fixture_root.glob("*.json"))
        self.assertEqual(sorted(set(referenced)), fixtures)


if __name__ == "__main__":
    unittest.main()
