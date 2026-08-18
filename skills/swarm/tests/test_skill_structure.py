from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SKILL = SKILL_ROOT / "SKILL.md"
EVALS = SKILL_ROOT / "evals" / "evals.json"


def doctrine() -> str:
    return "\n".join(
        (SKILL_ROOT / relative).read_text(encoding="utf-8")
        for relative in (
            "SKILL.md",
            "references/hierarchy.md",
            "references/task-contract.md",
            "references/monitoring.md",
            "references/review-contract.md",
            "references/design-guide.md",
        )
    )

sys.path.insert(0, str(SKILL_ROOT / "scripts"))
from verify_plugin_install import verify


class SwarmSkillStructureTests(unittest.TestCase):
    def test_install_verifier_requires_complete_declared_skill_tree_hash_parity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, installed = root / "source", root / "installed"
            for plugin in (source, installed):
                (plugin / ".codex-plugin").mkdir(parents=True)
                (plugin / "skills" / "swarm" / "references").mkdir(parents=True)
                (plugin / ".codex-plugin" / "plugin.json").write_text('{"skills":"./skills/"}', encoding="utf-8")
                (plugin / "skills" / "swarm" / "SKILL.md").write_text("swarm", encoding="utf-8")
                (plugin / "skills" / "swarm" / "references" / "task-contract.md").write_text("contract", encoding="utf-8")
            self.assertEqual(verify(source, installed), 3)
            (installed / "skills" / "swarm" / "SKILL.md").unlink()
            with self.assertRaisesRegex(ValueError, "skills/swarm/SKILL.md"):
                verify(source, installed)

    def test_core_skill_stays_below_500_lines(self) -> None:
        self.assertLess(len(SKILL.read_text(encoding="utf-8").splitlines()), 550)

    def test_eval_fixtures_are_structurally_valid(self) -> None:
        payload = json.loads(EVALS.read_text(encoding="utf-8"))
        evals = payload["evals"]
        ids = [item["id"] for item in evals]
        self.assertEqual(ids, list(range(1, len(evals) + 1)))
        self.assertEqual(
            sum("read-only config loader" in item["prompt"] for item in evals),
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
        skill = doctrine()
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

        self.assertIn("`UNVERIFIED` is an open acceptance failure", skill)
        self.assertIn("shallowest structure", skill)
        self.assertIn("canonical state", skill)
        self.assertIn("independent REVIEW", skill)
        self.assertIn("persistent SPECIALIST", hierarchy)
        self.assertRegex(hierarchy, r"(?s)Materialize ASSIST\s+and ADVISOR only")
        self.assertIn("independent `ACCEPTANCE` route", skill)
        self.assertIn("SPECIALIST interface", task_contract)
        self.assertIn("temporary wildcard", task_contract)
        self.assertIn("multiple ARCHITECTs, MOTHERs, or DEVELOPERs", task_contract)
        self.assertIn("Integration-ready", task_contract)
        self.assertIn("composed render comparison", task_contract)
        self.assertIn("composed rendered product", review_contract)
        self.assertIn("required proof blocks approval", review_contract)

    def test_task_titles_compress_real_role_authority_and_artifact(self) -> None:
        skill = doctrine()
        hierarchy = (SKILL_ROOT / "references" / "hierarchy.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("name DOERs by their real job", skill)
        self.assertIn("<domain emoji>LEAD - <responsibility>", skill)
        self.assertIn("<role emoji><PROFESSION> - <truth surface>", skill)
        self.assertIn("exactly one configured role icon", skill)
        self.assertIn("A title is a readability signal, never an\nauthority token", hierarchy)

    def test_octopus_is_default_configurable_ctrl_title_prefix(self) -> None:
        skill = doctrine()
        hierarchy = (SKILL_ROOT / "references" / "hierarchy.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("# 🐙 SWARM", skill)
        self.assertIn("CTRL is the sole root and owns intake", skill)
        self.assertIn("With role icons enabled", hierarchy)
        self.assertIn("🐙CTRL", skill)
        self.assertIn("🐙CTRL", hierarchy)

    def test_new_swarm_objective_starts_as_durable_ctrl(self) -> None:
        skill = doctrine()
        hierarchy = (SKILL_ROOT / "references" / "hierarchy.md").read_text(
            encoding="utf-8"
        )
        task_contract = (SKILL_ROOT / "references" / "task-contract.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("🐙CTRL - <objective>", skill)
        self.assertIn("Step 0", skill)
        self.assertIn("verif", skill.lower())
        self.assertIn("exact blocker", skill)
        self.assertIn("truthful internal CTRL identity", skill)
        self.assertIn("durable goal", skill)
        self.assertIn("subagent", skill)
        self.assertIn("CTRL is the sole root", hierarchy)
        self.assertIn("The specialist persists one exact cross-cutting truth surface", task_contract)
        self.assertIn("concise specific objective", skill)
        self.assertIn("task-title tool", skill)
        self.assertIn("and pin it. Verify both receipts", skill)
        self.assertIn("before durable-goal inspection", skill)
        self.assertLess(skill.index("**Step 0, never defer:**"), skill.index("Then inspect or create"))
        self.assertNotIn("🐙CTRL - <project> - <detailed descriptor>", skill)
        self.assertNotIn("🐙CTRL - <project> - <detailed descriptor>", hierarchy)
        self.assertNotIn("🐙CTRL - <project> - <detailed descriptor>", task_contract)
        self.assertIn("pending creation receipt reserves", skill)
        self.assertIn("pending creation receipt", hierarchy)
        self.assertIn("archive it", skill)
        self.assertIn("CTRL is the sole root and final composed authority", hierarchy)

    def test_closeout_archives_terminal_host_tasks_and_reports_failures(self) -> None:
        skill = doctrine()
        self.assertIn("accepting owner inventories every visible task it created or superseded", skill)
        self.assertIn("archive through the host control, and verify the receipt", skill)
        self.assertIn("Archive failure is an exact CTRL blocker", skill)
        self.assertIn("Archive a finite CTRL after its final handoff.", skill)

    def test_topology_and_evolution_are_general_subtractive_contracts(self) -> None:
        skill = doctrine()
        hierarchy = (SKILL_ROOT / "references" / "hierarchy.md").read_text(encoding="utf-8")

        self.assertIn("cross-lane dependency", skill)
        self.assertRegex(hierarchy, r"(?s)Artifact\s+count.*never\s+justify a lane")
        self.assertIn("consolidate rather than add incident clauses", skill)

    def test_product_review_subtracts_chrome_without_erasing_state_or_accessibility(self) -> None:
        review = (SKILL_ROOT / "references" / "review-contract.md").read_text(encoding="utf-8")

        self.assertIn("every visible UI element helps the user act or understand", review)
        self.assertIn("the current state", review)
        self.assertIn("Keep conditional\n   recovery controls hidden until their recovery state applies", review)
        self.assertIn("remove\n   self-evident identity or duplicate cues", review)
        self.assertIn("Prefer conventional icon-only actions", review)
        self.assertIn("require an accessible name and adequate\n   target", review)
        self.assertIn("ambiguous or consequential actions retain visible text", review)
        self.assertIn("Minimalism\n   cannot justify mystery icons, inaccessible targets, or removal of necessary\n   state", review)

    def test_visual_review_starts_from_the_user_visible_reality(self) -> None:
        review = (SKILL_ROOT / "references" / "review-contract.md").read_text(encoding="utf-8")

        self.assertIn("perform a first-glance user\nreality check", review)
        self.assertIn("A map\nwithout geography", review)
        self.assertIn("correct overlay on a blank, mocked, placeholder, failed,\nor fallback substrate", review)
        self.assertIn("console errors, warnings, page errors,\nnetwork failures", review)
        self.assertIn("duplicate actions, controls\nthat compete for the same job", review)

    def test_non_design_review_stops_at_good_enough_without_weakening_design(self) -> None:
        skill = doctrine()
        review = (SKILL_ROOT / "references" / "review-contract.md").read_text(encoding="utf-8")
        design = (SKILL_ROOT / "references" / "design-guide.md").read_text(encoding="utf-8")

        self.assertIn("Review and correction must be materially worthwhile", skill)
        self.assertIn("observable improvement that outweighs the work", skill)
        self.assertIn("Design may refine granular craft", skill)
        self.assertIn("Apply a significance gate outside design", review)
        self.assertIn("Do not record them as P3, backlog, optional\nfollow-up", review)
        self.assertIn("The act of reviewing is not evidence that a\nchange is valuable", review)
        self.assertIn("Design review is the explicit exception", review)
        self.assertIn("In mixed reviews, classify each finding\nbefore applying the exception", review)
        self.assertIn("[design-guide.md]", skill)
        self.assertIn("Small design details compound and design nitpicking is encouraged", design)
        self.assertIn("invariant, contextual default, or taste direction", design)

    def test_durable_goals_and_optional_watchdog_are_fixed_contracts(self) -> None:
        skill = doctrine()
        hierarchy = (SKILL_ROOT / "references" / "hierarchy.md").read_text(encoding="utf-8")
        task_contract = (SKILL_ROOT / "references" / "task-contract.md").read_text(encoding="utf-8")
        monitoring = (SKILL_ROOT / "references" / "monitoring.md").read_text(encoding="utf-8")
        config = (SKILL_ROOT / "references" / "config.md").read_text(encoding="utf-8")

        for text in (skill, hierarchy, task_contract, config):
            self.assertIn("durable", text)
            self.assertIn("exact", text)
        self.assertIn("Every durable CTRL, LEAD, and persistent SPECIALIST", skill)
        self.assertIn("exactly one matching durable goal", skill)
        self.assertIn("Goal controls are required", config)
        self.assertIn("# Optional alert-only WATCHDOG", monitoring)
        self.assertIn("An unbound goal has no watchdog clock", monitoring)
        self.assertRegex(monitoring, r"exactly three\s+checks")
        self.assertIn("Owner-heard micro-review after an alert", monitoring)
        self.assertIn("same-constraints counterfactual", monitoring)
        self.assertNotIn("SUPERVISOR", monitoring)

    def test_ctrl_stream_is_quiet_compact_and_not_templated(self) -> None:
        skill = doctrine()
        monitoring = (SKILL_ROOT / "references" / "monitoring.md").read_text(encoding="utf-8")
        evals = (SKILL_ROOT / "evals" / "evals.json").read_text(encoding="utf-8")

        self.assertIn("human review feed, not a management log", skill)
        self.assertIn("At the next safe boundary", skill)
        self.assertIn("smallest decisive inline proof", skill)
        self.assertIn("Unchanged snapshots remain silent", monitoring)
        self.assertNotIn("<title> — <state>", monitoring)
        self.assertIn('"id": 79', evals)
        self.assertIn("Workers are not asked to report more often", evals)

    def test_boost_eval_wording_does_not_disable_durable_owner_goals(self) -> None:
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
                "Mandatory CTRL, LEAD, and persistent SPECIALIST goal inspection"
            ),
            2,
        )

    def test_ctrl_operator_boundary_preserves_small_direct_work_and_delegates_visuals(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        hierarchy = (SKILL_ROOT / "references" / "hierarchy.md").read_text(encoding="utf-8")
        task_contract = (SKILL_ROOT / "references" / "task-contract.md").read_text(encoding="utf-8")
        evals = json.loads(EVALS.read_text(encoding="utf-8"))

        self.assertIn("CTRL is the operator/orchestrator, not the producer", skill)
        self.assertIn("CTRL is an operator, not a producer", hierarchy)
        self.assertIn("image-generation", skill)
        self.assertIn("IMAGEGEN", hierarchy)
        for text in (skill, hierarchy):
            self.assertIn("small", text.casefold())
            self.assertIn("DESIGNER", text)
            self.assertIn("stop", text.casefold())
        self.assertIn("Only `GENERAL` can pass the CTRL_DIRECT predicate", task_contract)
        self.assertIn("Every agent may request a role skill", skill)
        self.assertIn("`NORMAL_SUBAGENT`", skill)
        self.assertIn("Medium or large work must open a visible Codex task", skill)
        self.assertIn("`CTRL -> SUBAGENT` is not a substitute", hierarchy)
        visual_eval = next(item for item in evals["evals"] if item["id"] == 90)
        self.assertIn("mockup", visual_eval["prompt"].casefold())
        self.assertIn("DESIGNER", visual_eval["expected_output"])
        self.assertIn("CTRL_DIRECT", " ".join(visual_eval["assertions"]))


if __name__ == "__main__":
    unittest.main()
