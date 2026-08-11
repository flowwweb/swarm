from pathlib import Path
import unittest


class ProofClassificationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (Path(__file__).parents[1] / "SKILL.md").read_text(encoding="utf-8")

    def test_client_count_does_not_upgrade_substituted_transport(self):
        self.assertIn("Classify runtime proof by the authority and transport actually exercised", self.skill)
        self.assertIn("Multiple clients using mocks, request interception, fixtures, or an in-memory substitute", self.skill)
        self.assertIn("they do not prove the real local session, emulator, provider, network, or deployed path", self.skill)

    def test_receipt_names_substitution_and_unverified_boundaries(self):
        self.assertIn("Name the substituted boundary in the receipt", self.skill)
        self.assertIn("keep every unexercised boundary `UNVERIFIED`", self.skill)


if __name__ == "__main__":
    unittest.main()
