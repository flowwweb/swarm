import json
from pathlib import Path
import unittest


class ProofClassificationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill_root = Path(__file__).parents[1]
        cls.skill = (cls.skill_root / "SKILL.md").read_text(encoding="utf-8")
        payload = json.loads((cls.skill_root / "evals" / "evals.json").read_text(encoding="utf-8"))
        cls.evals = {entry["id"]: entry for entry in payload["evals"]}

    def test_client_count_does_not_upgrade_substituted_transport(self):
        self.assertIn("Classify runtime proof by the authority and transport actually exercised", self.skill)
        self.assertIn("Multiple clients using mocks, request interception, fixtures, or an in-memory substitute", self.skill)
        self.assertIn("they do not prove the real local session, emulator, provider, network, or deployed path", self.skill)

    def test_receipt_names_substitution_and_unverified_boundaries(self):
        self.assertIn("Name the substituted boundary in the receipt", self.skill)
        self.assertIn("keep every unexercised boundary `UNVERIFIED`", self.skill)

    def test_visual_acceptance_requires_the_claimed_substrate_and_clean_runtime(self):
        self.assertIn("inspect the exact rendered frame before trusting DOM geometry or receipts", self.skill)
        self.assertIn("a blank, fallback, mocked, placeholder, or failed substrate", self.skill)
        self.assertIn("Relevant console errors, warnings, page errors, and failed requests", self.skill)

    def test_visual_acceptance_evals_contrast_failed_and_exact_scope_proof(self):
        rejected = self.evals[86]
        accepted = self.evals[87]

        self.assertIn("Reject visual acceptance", rejected["expected_output"])
        self.assertIn("A correct overlay cannot substitute for the claimed primary substrate", rejected["assertions"])
        self.assertIn("Relevant warnings and failed requests block a clean-browser claim", rejected["assertions"])

        self.assertIn("Accept the browser visual evidence for the exact observed editor interaction", accepted["expected_output"])
        self.assertIn("The exact final frame visibly contains the real claimed substrate", accepted["assertions"])
        self.assertIn("The claimed user and task context are visibly relevant to the interaction", accepted["assertions"])
        self.assertIn("Relevant console, page-error, and network evidence is clean", accepted["assertions"])
        self.assertIn("Unexercised provider, deployed, and physical-device boundaries remain UNVERIFIED", accepted["assertions"])


if __name__ == "__main__":
    unittest.main()
