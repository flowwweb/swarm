from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SKILL = SKILL_ROOT / "SKILL.md"
EVALS = SKILL_ROOT / "evals" / "evals.json"

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
                (plugin / "skills" / "rush").mkdir(parents=True)
                (plugin / ".codex-plugin" / "plugin.json").write_text('{"skills":"./skills/"}', encoding="utf-8")
                (plugin / "skills" / "swarm" / "SKILL.md").write_text("swarm", encoding="utf-8")
                (plugin / "skills" / "swarm" / "references" / "task-contract.md").write_text("contract", encoding="utf-8")
                (plugin / "skills" / "rush" / "SKILL.md").write_text("rush", encoding="utf-8")
            self.assertEqual(verify(source, installed), 4)
            (installed / "skills" / "rush" / "SKILL.md").unlink()
            with self.assertRaisesRegex(ValueError, "skills/rush/SKILL.md"):
                verify(source, installed)

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
        self.assertIn("CTRL owns topology unless MOTHER exists", skill)
        self.assertIn("MOTHER alone changes execution topology", skill)
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
        self.assertIn("Format worker titles `<one literal emoji><ROLE> - <specific artifact>`", skill)
        self.assertIn("opening CTRL title is the Step 0 exception and never has an emoji", skill)
        self.assertIn("the shortest unambiguous title wins", skill)
        self.assertIn("Generic role types do not dictate task names", hierarchy)

    def test_octopus_is_product_brand_but_not_ctrl_title_prefix(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        hierarchy = (SKILL_ROOT / "references" / "hierarchy.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("# 🐙 SWARM", skill)
        self.assertIn("CTRL owns intake", skill)
        self.assertIn("with no emoji", hierarchy)
        self.assertNotIn("🐙CTRL", skill)
        self.assertNotIn("🐙CTRL", hierarchy)

    def test_new_swarm_objective_starts_as_durable_ctrl(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        hierarchy = (SKILL_ROOT / "references" / "hierarchy.md").read_text(
            encoding="utf-8"
        )
        task_contract = (SKILL_ROOT / "references" / "task-contract.md").read_text(
            encoding="utf-8"
        )
        for text in (skill, hierarchy, task_contract):
            self.assertIn("CTRL - <project> - <detailed descriptor>", text)
            self.assertIn("Step 0", text)
            self.assertIn("verif", text.lower())
            self.assertIn("exact blocker", text)
            self.assertIn("truthful internal CTRL identity", text)
        for text in (skill, hierarchy):
            self.assertIn("durable goal", text)
            self.assertIn("subagents", text)
        self.assertIn("project is mandatory", skill)
        self.assertIn("omit the descriptor only when none is useful", skill)
        self.assertIn("task-title tool", skill)
        self.assertIn("pins the current task", skill)
        self.assertIn("Verify successful title and pin receipts", skill)
        self.assertIn("before durable-goal inspection", skill)
        self.assertIn("before durable-goal inspection", hierarchy)
        self.assertLess(skill.index("**Step 0, never defer:**"), skill.index("After Step 0"))
        self.assertNotIn("🐙CTRL - <specific objective>", skill)
        self.assertNotIn("🐙CTRL - <specific objective>", hierarchy)
        self.assertNotIn("🐙CTRL - <specific objective>", task_contract)
        self.assertIn("pending creation receipt reserves", skill)
        self.assertIn("pending `clientThreadId`", hierarchy)
        self.assertIn("archive it", skill)
        self.assertIn("CTRL owns topology until the portfolio predicate", hierarchy)

    def test_closeout_archives_terminal_host_tasks_and_reports_failures(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn("Closeout is part of completion", skill)
        self.assertIn("inventories every visible task it created or superseded", skill)
        self.assertIn("call the host archive control", skill)
        self.assertIn("verify the archive receipt", skill)
        self.assertIn("superseded coordination version is stale", skill)
        self.assertIn("exact task ID and error", skill)
        self.assertIn("archive a finite CTRL after its final handoff", skill)

    def test_topology_and_evolution_are_general_subtractive_contracts(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        hierarchy = (SKILL_ROOT / "references" / "hierarchy.md").read_text(encoding="utf-8")

        self.assertIn("multiple distinct ownership lanes", skill)
        self.assertIn("Artifact or variant count", hierarchy)
        self.assertIn("shared words do not establish identity", skill)
        self.assertIn("never accumulate incident clauses", skill)
        self.assertIn("remove superseded guidance", skill)
        self.assertIn("time to forward progress and net coordination load", skill)
        self.assertIn("non-material process imperfection", skill)

    def test_mandatory_goals_and_passive_heartbeat_are_fixed_contracts(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        hierarchy = (SKILL_ROOT / "references" / "hierarchy.md").read_text(encoding="utf-8")
        task_contract = (SKILL_ROOT / "references" / "task-contract.md").read_text(encoding="utf-8")
        monitoring = (SKILL_ROOT / "references" / "monitoring.md").read_text(encoding="utf-8")
        config = (SKILL_ROOT / "references" / "config.md").read_text(encoding="utf-8")

        for text in (skill, hierarchy, task_contract, config):
            self.assertIn("durable", text)
            self.assertIn("exact", text)
        self.assertIn("CTRL, MOTHER, every LEAD, and every persistent ARCHITECT", skill)
        self.assertIn("conflicting unfinished goal", skill)
        self.assertIn("Goal controls are required", config)
        self.assertIn("survives\ncompaction", monitoring)
        self.assertIn("Silence alone\nis not a stall", monitoring)
        self.assertIn("exactly one bounded same-surface recovery", monitoring)
        self.assertIn("unaffected lanes moving", monitoring)
        self.assertIn("polling loops, queues", monitoring)

    def test_ctrl_stream_is_quiet_compact_and_not_templated(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        monitoring = (SKILL_ROOT / "references" / "monitoring.md").read_text(encoding="utf-8")
        evals = (SKILL_ROOT / "evals" / "evals.json").read_text(encoding="utf-8")

        self.assertIn("CTRL is the live human review feed", skill)
        self.assertIn("Keep non-visual coordination clean and compact", skill)
        self.assertIn("one reserved natural line", skill)
        self.assertIn("unchanged state quiet", skill)
        self.assertIn("At the next safe message boundary", skill)
        self.assertIn("worker final, artifact path, folder link", skill)
        self.assertIn("self-contained plain caption", skill)
        self.assertIn("Missing disposition or surface receipt remains an open acceptance failure", skill)
        self.assertIn("Never template status or increase worker reporting", skill)
        self.assertIn("a passive snapshot is not itself an update", monitoring)
        self.assertNotIn("<title> — <state>", monitoring)
        self.assertIn('"id": 79', evals)
        self.assertIn("Workers are not asked to report more often", evals)

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
