from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = SKILL_ROOT.parents[1]
ROLE_ROOT = SKILL_ROOT / "roles"
REQUIRED_DEFAULTS = frozenset({"designer.md", "developer.md", "architect.md", "reviewer.md"})

sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
from build_package import source_file_hashes


class RoleCardTests(unittest.TestCase):
    def test_role_cards_are_a_dynamic_filename_registry_and_shipped(self) -> None:
        cards = sorted(ROLE_ROOT.glob("*.md"))
        self.assertTrue(REQUIRED_DEFAULTS.issubset({card.name for card in cards}))

        packaged_files = source_file_hashes(REPOSITORY_ROOT)
        for card in cards:
            with self.subTest(card=card.name):
                lines = card.read_text(encoding="utf-8").splitlines()
                self.assertRegex(lines[0], r"^# .+")
                content = [line for line in lines[1:] if line.strip()]
                self.assertEqual(len(content), 12)
                self.assertTrue(all(re.fullmatch(r"\d+\. .+[.!?]", line) for line in content))
                self.assertEqual(
                    [int(line.split(". ", 1)[0]) for line in content], list(range(1, 13))
                )
                priority_line = content[0].lower()
                self.assertTrue(
                    all(term in priority_line for term in ("user direction", "project truth", "outrank"))
                )
                self.assertIn(f"skills/swarm/roles/{card.name}", packaged_files)


if __name__ == "__main__":
    unittest.main()
