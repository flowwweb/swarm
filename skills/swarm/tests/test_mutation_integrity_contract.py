import unittest
from pathlib import Path


class MutationIntegrityContractTests(unittest.TestCase):
    def test_failed_writes_keep_recovery_exact_and_non_destructive(self):
        skill = (Path(__file__).parents[1] / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(skill, r"(?is)failed, timed-out, or non-atomic writes? as untrusted.*exact target.*diff scope.*preserve pre-existing.*verified baseline/backup.*smaller patches.*never broadly roll back")


if __name__ == "__main__":
    unittest.main()
