from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "references" / "proven-solutions.md"
EVALS = ROOT / "evals" / "proven-solutions.json"


class ProvenSolutionContractTests(unittest.TestCase):
    def test_policy_prefers_fitting_available_solutions_without_forcing_them(self) -> None:
        policy = POLICY.read_text(encoding="utf-8")

        self.assertRegex(policy, r"(?is)user.*outcome.*authority boundary first")
        self.assertRegex(policy, r"(?is)maintained project primitives.*already-available.*skills/plugins.*documented platform workflows")
        self.assertRegex(policy, r"(?is)available, compatible, sufficiently\s+inspectable.*integration, operational, and learning cost")
        self.assertRegex(policy, r"(?is)smallest established primitive.*rather than copying")
        for mismatch in ("no candidate fits", "cost exceeds the benefit", "opaque, insecure", "unreliable, slower/heavier"):
            self.assertIn(mismatch, policy)

    def test_policy_preserves_authority_proof_and_low_friction(self) -> None:
        policy = POLICY.read_text(encoding="utf-8")

        self.assertRegex(policy, r"(?is)Never install.*authenticate.*grant permissions to, send\s+data to.*without the\s+authority")
        self.assertRegex(policy, r"(?is)not create a fixed catalog.*mandate a plugin.*discovery ritual")
        self.assertRegex(policy, r"(?is)Low-risk, obvious fits need no research log")
        for boundary in ("cannot transfer\n   acceptance", "conceal a substituted boundary", "local proof"):
            self.assertIn(boundary, policy)

    def test_evals_cover_reuse_mismatch_authority_and_no_ceremony_contrasts(self) -> None:
        payload = json.loads(EVALS.read_text(encoding="utf-8"))
        cases = {case["id"]: case for case in payload["cases"]}

        self.assertEqual(
            set(cases),
            {
                "reuse-fitting-installed-workflow",
                "build-on-mismatch",
                "authority-before-external-reuse",
                "no-ceremony-for-obvious-fit",
            },
        )
        self.assertIn("Use the installed workflow", cases["reuse-fitting-installed-workflow"]["expected"])
        self.assertIn("smallest local solution", cases["build-on-mismatch"]["expected"])
        self.assertIn("Do not contact", cases["authority-before-external-reuse"]["expected"])
        self.assertIn("do not create a tool survey", cases["no-ceremony-for-obvious-fit"]["expected"])


if __name__ == "__main__":
    unittest.main()
