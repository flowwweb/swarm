from __future__ import annotations

import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


class MutationIntegrityContractTests(unittest.TestCase):
    def test_failed_writes_require_exact_target_recovery_and_smaller_reapplication(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")

        self.assertIn("failed, timed-out, or non-atomic write as untrusted", skill)
        self.assertIn("exact-target integrity and intended diff scope", skill)
        self.assertIn("preserve pre-existing edits", skill)
        self.assertIn("recover from a verified baseline or backup", skill)
        self.assertIn("reapply in smaller bounded patches", skill)
        self.assertIn("never use a broad rollback", skill)


if __name__ == "__main__":
    unittest.main()
