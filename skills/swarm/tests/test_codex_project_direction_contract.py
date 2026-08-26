import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = ROOT / "skills" / "swarm"
PLUGIN_ROOT = ROOT / "plugins" / "swarm"


class CodexProjectDirectionContractTests(unittest.TestCase):
    def test_root_brief_is_one_schema_bound_non_secret_document(self) -> None:
        text = (ROOT / "SWARM.md").read_text(encoding="utf-8")
        match = re.search(
            r"<!-- swarm-project-brief:schema=(\d+) -->\s*```json\s*(.*?)\s*```",
            text,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "1")
        payload = json.loads(match.group(2))
        required = {
            "schema_version", "updated_at", "project", "users_outcomes",
            "objective", "repo", "authority", "milestones", "decisions",
            "ownership", "proof_acceptance", "risks_blockers", "links",
        }
        self.assertEqual(set(payload), required)
        self.assertEqual(payload["schema_version"], 1)
        self.assertNotRegex(text, re.compile(r"api[_ -]?key|secret|token|private key|raw prompt", re.I))

    def test_dispatch_brief_and_decision_contracts_are_explicit(self) -> None:
        brief = re.sub(r"\s+", " ", (SKILL_ROOT / "references" / "project-brief.md").read_text(encoding="utf-8"))
        decision = re.sub(r"\s+", " ", (SKILL_ROOT / "references" / "decision-set.md").read_text(encoding="utf-8"))
        for required in ("exactly one root", "binds its digest", "UNREADY", "deterministic schema transform", "one atomic update"):
            self.assertIn(required, brief)
        for required in ("exactly one candidate is `SELECTED`", "every other candidate", "hash-bound receipt", "exact path", "no glob", "Storage", "does not start a worker, process, or service"):
            self.assertIn(required, decision)

    def test_codex_is_the_only_agent_host_surface_and_external_proof_terms_remain(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        model_doc = (SKILL_ROOT / "references" / "model-providers.md").read_text(encoding="utf-8")
        self.assertIn("Codex-native", readme)
        for unsupported_install in (
            "claude plugin marketplace",
            "gemini extensions install",
            "github copilot, cursor, opencode",
        ):
            self.assertNotIn(unsupported_install, readme.casefold())
        for unsupported in ("Anthropic", "Qwen", "Kimi", "Claude Code", "Gemini CLI"):
            self.assertNotIn(unsupported, model_doc)
        self.assertIn("external-provider proof", model_doc.casefold())

    def test_unsupported_host_manifests_are_not_advertised(self) -> None:
        for root in (ROOT, PLUGIN_ROOT):
            self.assertFalse((root / ".claude-plugin" / "marketplace.json").exists())
            self.assertFalse((root / ".claude-plugin" / "plugin.json").exists())
            self.assertFalse((root / "gemini-extension.json").exists())
        self.assertTrue((ROOT / ".codex-plugin" / "plugin.json").is_file())

    def test_policy_docs_mirror_exactly(self) -> None:
        for relative in (
            Path("SKILL.md"),
            Path("references") / "config.md",
            Path("references") / "decision-set.md",
            Path("references") / "hierarchy.md",
            Path("references") / "model-providers.md",
            Path("references") / "project-brief.md",
            Path("references") / "review-contract.md",
            Path("references") / "task-contract.md",
            Path("assets") / "swarm-config.toml",
        ):
            self.assertEqual(
                (SKILL_ROOT / relative).read_bytes(),
                (PLUGIN_ROOT / "skills" / "swarm" / relative).read_bytes(),
                relative.as_posix(),
            )


if __name__ == "__main__":
    unittest.main()
