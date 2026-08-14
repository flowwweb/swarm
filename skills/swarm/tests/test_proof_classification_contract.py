import json
from pathlib import Path
import unittest


class ProofClassificationContractTests(unittest.TestCase):
    def test_core_routes_transport_and_visual_truth_to_review_contract(self):
        root = Path(__file__).parents[1]
        core = (root / "SKILL.md").read_text(encoding="utf-8")
        review = (root / "references" / "review-contract.md").read_text(encoding="utf-8")
        self.assertIn("Load the review contract before accepting visual", core)
        self.assertRegex(review, r"(?is)authority and transport.*substituted boundary.*UNVERIFIED")
        self.assertRegex(review, r"(?is)exact final rendered frame.*primary substrate.*correct overlay cannot upgrade")

    def test_visual_acceptance_evals_contrast_failed_and_exact_scope_proof(self):
        root = Path(__file__).parents[1]
        payload = json.loads((root / "evals" / "evals.json").read_text(encoding="utf-8"))
        evals = {entry["id"]: entry for entry in payload["evals"]}
        self.assertIn("Reject visual acceptance", evals[86]["expected_output"])
        self.assertIn("Accept the browser visual evidence", evals[87]["expected_output"])
        self.assertTrue(any("UNVERIFIED" in item for item in evals[87]["assertions"]))


if __name__ == "__main__":
    unittest.main()
