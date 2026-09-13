from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = SKILL_ROOT.parents[1]
ROLE_ROOT = SKILL_ROOT / "roles"
PLUGIN_ROLE_ROOT = REPOSITORY_ROOT / "plugins" / "swarm" / "skills" / "swarm" / "roles"
EXPECTED_CARDS = {
    "manager": "Manager", "strategist": "Strategist", "researcher": "Researcher",
    "analyst": "Analyst", "specialist": "Specialist", "inventor": "Inventor",
    "architect": "Architect", "designer": "Designer", "artist": "Artist",
    "writer": "Writer", "developer": "Dev", "producer": "Producer",
    "tester": "Tester", "assistant": "Assistant", "security": "Security",
    "auditor": "Auditor", "legal": "Legal", "reviewer": "Reviewer",
    "operator": "Operator", "marketer": "Marketer", "support": "Support",
    "accountant": "Accountant", "recruiter": "Recruiter", "educator": "Educator",
}
EXPECTED_FOCUS = {
    "manager": ("plan", "dependencies"), "strategist": ("options", "tradeoffs"),
    "researcher": ("source", "confidence"), "analyst": ("reproducible", "uncertainty"),
    "specialist": ("domain", "standards"), "inventor": ("hypothesis", "prototype"),
    "architect": ("interface", "migration"), "designer": ("interaction", "accessibility"),
    "artist": ("visual", "reference"), "writer": ("publication", "claims"),
    "developer": ("implementation", "test"), "producer": ("production", "rights"),
    "tester": ("scenario", "reproducible"), "assistant": ("organized", "follow-up"),
    "security": ("threat", "residual risk"), "auditor": ("criteria", "evidence"),
    "legal": ("jurisdiction", "primary"), "reviewer": ("criteria", "findings"),
    "operator": ("runbook", "recovery"), "marketer": ("positioning", "measurement"),
    "support": ("reproduction", "escalation"), "accountant": ("reconcil", "adjustments"),
    "recruiter": ("scorecard", "candidates"), "educator": ("mastery", "assessment"),
}

sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
from build_package import source_file_hashes


class RoleCardTests(unittest.TestCase):
    def test_role_cards_are_the_exact_four_section_profession_registry(self) -> None:
        cards = sorted(ROLE_ROOT.glob("*.md"))
        self.assertEqual(len(cards), 24)
        self.assertEqual({card.stem for card in cards}, set(EXPECTED_CARDS))

        packaged_files = source_file_hashes(REPOSITORY_ROOT)
        for card in cards:
            with self.subTest(card=card.name):
                lines = card.read_text(encoding="utf-8").splitlines()
                content = [line for line in lines if line.strip()]
                headings = ["## PURPOSE", "## OWNERSHIP", "## BOUNDARIES", "## ESCALATION"]
                heading_indexes = [index for index, line in enumerate(content) if line.startswith("## ")]
                self.assertEqual(content[:2], [f"# {EXPECTED_CARDS[card.stem]}", headings[0]])
                self.assertEqual([content[index] for index in heading_indexes], headings)
                purpose = content[heading_indexes[0] + 1:heading_indexes[1]]
                ownership = content[heading_indexes[1] + 1:heading_indexes[2]]
                boundaries = content[heading_indexes[2] + 1:heading_indexes[3]]
                escalation = content[heading_indexes[3] + 1:]
                self.assertEqual(len(purpose), 1)
                self.assertTrue(re.fullmatch(r"[^#-].*[.!?]", purpose[0]))
                self.assertTrue(3 <= len(ownership) <= 5)
                self.assertTrue(1 <= len(boundaries) <= 3)
                self.assertTrue(1 <= len(escalation) <= 2)
                self.assertTrue(all(re.fullmatch(r"- .+[.!?]", line) for line in (*ownership, *boundaries, *escalation)))
                normalized = "\n".join(content).casefold()
                for expected in EXPECTED_FOCUS[card.stem]:
                    self.assertIn(expected, normalized)
                self.assertIn(f"skills/swarm/roles/{card.name}", packaged_files)
                self.assertEqual(card.read_bytes(), (PLUGIN_ROLE_ROOT / card.name).read_bytes())

    def test_retired_or_structural_labels_are_not_role_cards(self) -> None:
        self.assertFalse((ROLE_ROOT / "mother.md").exists())
        self.assertFalse((ROLE_ROOT / "watchdog.md").exists())
        self.assertFalse((ROLE_ROOT / "ctrl.md").exists())
        self.assertFalse((ROLE_ROOT / "critic.md").exists())
        self.assertFalse((ROLE_ROOT / "content_creator.md").exists())

    def test_cards_are_semantic_not_governance_templates(self) -> None:
        purposes = []
        for path in ROLE_ROOT.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            lines = [line for line in text.splitlines() if line.strip()]
            purposes.append(lines[lines.index("## PURPOSE") + 1])
            self.assertIsNone(re.search(
                r"\b(SWARM|CTRL|LEAD|DOER|structural|authority|acceptance|user direction|"
                r"project truth|claim limit|profession perspective|profession guidance)\b",
                text,
                re.I,
            ))
            self.assertNotIn("Recommendations:", text)
            for skill_id in (
                "find-skills", "frontend-design", "systematic-debugging",
                "test-driven-development", "verification-before-completion", "webapp-testing",
            ):
                self.assertNotIn(skill_id, text)
        self.assertEqual(len(purposes), len(set(purposes)))

    def test_global_guidance_is_composed_once_and_repo_guidance_is_scoped(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        cards = "\n".join(path.read_text(encoding="utf-8") for path in ROLE_ROOT.glob("*.md"))
        guidance = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(skill.count("Global policy is composed once"), 1)
        self.assertNotIn("Global policy is composed once", cards)
        recovery = "references/runtime-recovery.md"
        self.assertIn(f"[runtime-recovery.md]({recovery})", skill)
        lab = "references/lab-workflow.md"
        self.assertIn(f"[Lab workflow]({lab})", skill)
        lab_contract = (SKILL_ROOT / lab).read_text(encoding="utf-8")
        self.assertRegex(lab_contract, r"existing milestone, task, block, artifact, decision-set, proof, and review\s+contracts")
        self.assertIn("every role follows", skill)
        task_contract = (SKILL_ROOT / "references/task-contract.md").read_text(encoding="utf-8")
        self.assertIn("[recovery loop](runtime-recovery.md)", task_contract)
        self.assertEqual((SKILL_ROOT / recovery).read_bytes(), (PLUGIN_ROLE_ROOT.parent / recovery).read_bytes())
        self.assertEqual((SKILL_ROOT / lab).read_bytes(), (PLUGIN_ROLE_ROOT.parent / lab).read_bytes())
        self.assertIn("skills/swarm/SKILL.md", guidance)
        self.assertIn("plugins/swarm/", guidance)
        self.assertIn("Commit Guard", guidance)
        self.assertLessEqual(len(guidance.splitlines()), 100)


if __name__ == "__main__":
    unittest.main()
