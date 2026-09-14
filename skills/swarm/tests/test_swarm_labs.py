import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "swarm_labs.py"
CATALOG = Path(__file__).resolve().parents[1] / "labs" / "catalog.json"
SPEC = importlib.util.spec_from_file_location("swarm_labs", SCRIPT)
swarm_labs = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(swarm_labs)


class SwarmLabsTests(unittest.TestCase):
    def setUp(self):
        self.manifest = swarm_labs.validate_manifest(json.loads(swarm_labs.DEFAULT_MANIFEST.read_text(encoding="utf-8")))

    def run_result(self, candidate_id, codex_tokens):
        return {
            "lab_id": "coordination_recovery",
            "scenario_id": "small_repo_fix",
            "candidate_id": candidate_id,
            "accepted": True,
            "elapsed_ms": 100,
            "user_interventions": 0,
            "nonproductive_retries": 0,
            "codex_tokens": codex_tokens,
            "chatgpt_tokens": 50 if candidate_id == "usage_saver" else 0,
            "evidence": [f"receipt:{candidate_id}"],
        }

    def test_manifest_has_three_recommended_labs(self):
        self.assertEqual(
            [lab["id"] for lab in self.manifest["labs"]],
            ["prompt_context", "coordination_recovery", "hq_clarity"],
        )

    def test_user_catalog_is_thin_and_role_bound(self):
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        self.assertEqual([lab["id"] for lab in catalog["labs"]], ["product", "research", "design", "build", "test", "content", "growth", "ops"])
        allowed = {"id", "name", "icon", "summary", "outcome", "suggested_roles", "guide"}
        self.assertTrue(all(set(lab) == allowed and lab["suggested_roles"] and 2 <= len(lab["guide"]) <= 4 for lab in catalog["labs"]))
        self.assertEqual([step["value"] for step in catalog["manifest_contract"]["progress"]["steps"]], [.25, .5, .75, 1])
        self.assertNotIn("status", CATALOG.read_text(encoding="utf-8"))

    def test_savings_require_paired_measured_codex_tokens(self):
        runs = swarm_labs.validate_runs(
            {"runs": [self.run_result("astra_solo", 1000), self.run_result("usage_saver", 400)]},
            self.manifest,
        )
        estimate = swarm_labs.build_report(self.manifest, runs)["usage_saver_estimate"]
        self.assertEqual(estimate["status"], "MEASURED")
        self.assertEqual(estimate["pairs"][0]["estimated_codex_tokens_saved"], 600)

    def test_missing_baseline_keeps_savings_unknown(self):
        runs = swarm_labs.validate_runs(
            {"runs": [self.run_result("usage_saver", 400)]}, self.manifest
        )
        self.assertEqual(swarm_labs.build_report(self.manifest, runs)["usage_saver_estimate"]["status"], "UNKNOWN")

    def test_rejects_result_without_evidence(self):
        run = self.run_result("usage_saver", 400)
        run["evidence"] = []
        with self.assertRaisesRegex(swarm_labs.LabError, "requires evidence"):
            swarm_labs.validate_runs({"runs": [run]}, self.manifest)


if __name__ == "__main__":
    unittest.main()
