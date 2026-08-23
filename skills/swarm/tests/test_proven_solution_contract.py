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
        normalized = " ".join(policy.split())

        self.assertRegex(policy, r"(?is)user.*outcome.*authority boundary first")
        self.assertIn(
            "maintained project primitives, libraries already present in the target repo, "
            "already-available skills/plugins, documented platform workflows",
            normalized,
        )
        self.assertRegex(policy, r"(?is)available, compatible, sufficiently\s+inspectable.*total\s+cost")
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

    def test_policy_checks_library_fit_and_preserves_branding_and_custom_paths(self) -> None:
        policy = POLICY.read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        for check in (
            "accessibility",
            "visual consistency and branding",
            "bundle/runtime cost",
            "security/licensing",
            "maintenance",
            "SSR/browser compatibility",
            "existing framework",
        ):
            self.assertIn(check, normalized)
        self.assertIn("Do not add a dependency solely because it appears", normalized)
        self.assertIn("User-selected branding and product requirements override", normalized)
        self.assertRegex(policy, r"(?is)dependency-free/custom path.*no suitable library fits")
        self.assertRegex(policy, r"(?is)3D/effects, opt-in only.*not default decoration")

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
                "library-preferred-over-bespoke",
                "custom-on-no-fit",
            },
        )
        self.assertIn("Use the installed workflow", cases["reuse-fitting-installed-workflow"]["expected"])
        self.assertIn("smallest local solution", cases["build-on-mismatch"]["expected"])
        self.assertIn("Do not contact", cases["authority-before-external-reuse"]["expected"])
        self.assertIn("do not create a tool survey", cases["no-ceremony-for-obvious-fit"]["expected"])
        self.assertIn("Reuse the existing compatible library", cases["library-preferred-over-bespoke"]["expected"])
        self.assertIn("dependency-free custom path", cases["custom-on-no-fit"]["expected"])


if __name__ == "__main__":
    unittest.main()
