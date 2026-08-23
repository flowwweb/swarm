import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SKILL = REPOSITORY_ROOT / "skills" / "swarm" / "SKILL.md"
PLUGIN_SKILL = REPOSITORY_ROOT / "plugins" / "swarm" / "skills" / "swarm" / "SKILL.md"


class UserIntentFeedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = SKILL.read_text(encoding="utf-8")
        cls.plugin_skill = PLUGIN_SKILL.read_text(encoding="utf-8")

    def test_message_bursts_merge_compatible_intent(self):
        for text in (self.skill, self.plugin_skill):
            self.assertIn("one ordered intent feed", text)
            self.assertIn("A burst of messages is one logical turn", text)
            self.assertIn("reconcile all unseen user", text)
            self.assertIn("Never require the user to repeat a message", text)

    def test_active_owner_is_not_an_execution_gate(self):
        for text in (self.skill, self.plugin_skill):
            self.assertIn("active-owner and no-duplicate guards protect user custody", text)
            self.assertIn("not execution gates", text)
            self.assertIn("parent/master CTRL, peer", text)
            self.assertIn("`active` status alone is neither progress nor a", text)
            self.assertIn("reorient the existing owner within the same lane", text)

    def test_plugin_entrypoint_matches_canonical_skill(self):
        self.assertEqual(self.skill, self.plugin_skill)


if __name__ == "__main__":
    unittest.main()
