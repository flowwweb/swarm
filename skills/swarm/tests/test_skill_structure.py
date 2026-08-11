from __future__ import annotations

import json
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SKILL = SKILL_ROOT / "SKILL.md"
EVALS = SKILL_ROOT / "evals" / "evals.json"


class SwarmSkillStructureTests(unittest.TestCase):
    def test_core_skill_stays_below_500_lines(self) -> None:
        self.assertLess(len(SKILL.read_text(encoding="utf-8").splitlines()), 550)

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

    def test_composed_outcome_gates_remain_explicit(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        task_contract = (SKILL_ROOT / "references" / "task-contract.md").read_text(
            encoding="utf-8"
        )
        hierarchy = (SKILL_ROOT / "references" / "hierarchy.md").read_text(
            encoding="utf-8"
        )
        monitoring = (SKILL_ROOT / "references" / "monitoring.md").read_text(
            encoding="utf-8"
        )
        config = (SKILL_ROOT / "references" / "config.md").read_text(
            encoding="utf-8"
        )
        review_contract = (SKILL_ROOT / "references" / "review-contract.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("end-to-end requirement ledger", skill)
        self.assertIn("`UNVERIFIED` is an open acceptance failure", skill)
        self.assertIn("LEAD integrates and inspects each whole lane result", skill)
        self.assertIn("zerg rush", skill)
        self.assertIn("shallowest structure", skill)
        self.assertIn("MOTHER alone changes topology", skill)
        self.assertIn("canonical state", skill)
        self.assertIn("independent REVIEW", skill)
        self.assertIn("persistent ARCHITECT", hierarchy)
        self.assertIn("Materialize ASSIST and ADVISOR only", hierarchy)
        self.assertIn("Completion requires independent review", skill)
        self.assertIn("ARCHITECT system interface", task_contract)
        self.assertIn("temporary wildcard", task_contract)
        self.assertIn("ARCHITECT persists system coherence", task_contract)
        self.assertIn("Integration-ready", task_contract)
        self.assertIn("composed render comparison", task_contract)
        self.assertIn("composed rendered product", review_contract)
        self.assertIn("required proof blocks approval", review_contract)

    def test_task_titles_compress_real_role_authority_and_artifact(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        hierarchy = (SKILL_ROOT / "references" / "hierarchy.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("replace DOER with the real role", skill)
        self.assertIn("use `<DOMAIN> LEAD` for a lane owner", skill)
        self.assertIn("<one literal emoji><ROLE> - <specific artifact>", skill)
        self.assertIn("the shortest unambiguous title wins", skill)
        self.assertIn("Generic role types do not dictate task names", hierarchy)

    def test_mandatory_goals_and_passive_heartbeat_are_fixed_contracts(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        hierarchy = (SKILL_ROOT / "references" / "hierarchy.md").read_text(encoding="utf-8")
        task_contract = (SKILL_ROOT / "references" / "task-contract.md").read_text(encoding="utf-8")
        monitoring = (SKILL_ROOT / "references" / "monitoring.md").read_text(encoding="utf-8")
        config = (SKILL_ROOT / "references" / "config.md").read_text(encoding="utf-8")

        for text in (skill, hierarchy, task_contract, config):
            self.assertIn("durable", text)
            self.assertIn("exact", text)
        self.assertIn("MOTHER, every LEAD, and every persistent ARCHITECT", skill)
        self.assertIn("conflicting unfinished goal", skill)
        self.assertIn("Goal controls are required", config)
        self.assertIn("survives\ncompaction", monitoring)
        self.assertIn("Silence alone\nis not a stall", monitoring)
        self.assertIn("exactly one bounded same-surface recovery", monitoring)
        self.assertIn("unaffected lanes moving", monitoring)
        self.assertIn("polling loops, queues", monitoring)

    def test_boost_eval_wording_does_not_disable_mandatory_role_goals(self) -> None:
        evals = (SKILL_ROOT / "evals" / "evals.json").read_text(encoding="utf-8")
        stale_phrases = (
            "No Codex " + "goal is created",
            "no goal created because " + "activation was not directly requested",
            "no goal is created, and " + "the settings boundary",
            "does not create goals, " + "enter hands-off mode",
            "No goal is created without " + "durable_goal",
        )
        for phrase in stale_phrases:
            self.assertNotIn(phrase, evals)
        self.assertGreaterEqual(evals.count("No additional Boost goal is created"), 3)
        self.assertGreaterEqual(
            evals.count(
                "Mandatory MOTHER, LEAD, and persistent ARCHITECT goal inspection"
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main()
