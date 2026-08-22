import unittest
from pathlib import Path


class MutationIntegrityContractTests(unittest.TestCase):
    def test_failed_writes_keep_recovery_exact_and_non_destructive(self):
        skill = (Path(__file__).parents[1] / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(skill, r"(?is)failed, timed-out, or non-atomic writes? as untrusted.*exact target.*diff scope.*preserve pre-existing.*verified baseline/backup.*smaller patches.*never broadly roll back")

    def test_user_action_precedence_requires_host_owned_mutation_receipts(self):
        root = Path(__file__).parents[1]
        skill = (root / "SKILL.md").read_text(encoding="utf-8")
        task = (root / "references" / "task-contract.md").read_text(encoding="utf-8")
        hierarchy = (root / "references" / "hierarchy.md").read_text(encoding="utf-8")
        combined = "\n".join((skill, task, hierarchy))
        self.assertRegex(combined, r"(?is)user.*state.*(?:always win(?:s)?|always take precedence)")
        self.assertRegex(combined, r"(?is)rename.*pin.*archive.*state")
        self.assertRegex(combined, r"(?is)host task API.*explicit.user.*receipt")
        self.assertRegex(combined, r"(?is)(?:no mutation.*receipt|receipt.*(?:absent|without|conflicting).*no mutation)")
        self.assertRegex(combined, r"(?is)(?:no raw user text|without raw user text)")

    def test_step_zero_and_closeout_cannot_mutate_user_task_state_unconditionally(self):
        root = Path(__file__).parents[1]
        skill = (root / "SKILL.md").read_text(encoding="utf-8")
        task_contract = (root / "references" / "task-contract.md").read_text(encoding="utf-8")
        skill_step_zero = skill.split("**Step 0, never defer:**", 1)[1].split("\n\n", 1)[0]
        task_step_zero = task_contract.split("Step 0 first:", 1)[1].split("\n\n", 1)[0]
        for step_zero in (skill_step_zero, task_step_zero):
            self.assertRegex(step_zero, r"(?is)fresh host-owned receipt.*SWARM custody")
            self.assertRegex(step_zero, r"(?is)no user-created.*(?:pinned|state)")
            self.assertRegex(step_zero, r"(?is)only then may.*(?:title|pin)")
            self.assertRegex(step_zero, r"(?is)otherwise preserve.*user state")
        self.assertNotIn("set the current task title", skill_step_zero)
        self.assertNotIn("use the host task-title tool to set", task_step_zero)
        closeout = skill.split("Before a finite portfolio", 1)[1].split("\n\n", 1)[0]
        self.assertRegex(closeout, r"(?is)SWARM-created state.*current custody.*unpin.*archive")
        self.assertRegex(closeout, r"(?is)user-created.*remain untouched absent.*explicit-user receipt")
        self.assertIn("No unconditional unpin/archive is permitted", closeout)

    def test_storage_lane_and_senior_lane_heartbeat_contracts_are_explicit(self):
        root = Path(__file__).parents[1]
        hierarchy = (root / "references" / "hierarchy.md").read_text(encoding="utf-8")
        monitoring = (root / "references" / "monitoring.md").read_text(encoding="utf-8")
        combined = "\n".join((hierarchy, monitoring))
        self.assertRegex(combined, r"(?is)STORAGE LEAD.*exact target manifest")
        self.assertRegex(combined, r"(?is)active.process.*live.logs?.*databases?.*dirty")
        self.assertRegex(combined, r"(?is)copy.verify.remove|recoverable move")
        self.assertRegex(combined, r"(?is)one bounded wake per lane")
        self.assertRegex(combined, r"(?is)missing.*material.*receipt.*stall")
        self.assertRegex(combined, r"(?is)visible senior.*task|visible.*senior Codex")

    def test_visible_lane_boundary_contrasts_with_small_sidecar_capacity(self):
        root = Path(__file__).parents[1]
        hierarchy = (root / "references" / "hierarchy.md").read_text(encoding="utf-8")
        skill = (root / "SKILL.md").read_text(encoding="utf-8")
        combined = "\n".join((skill, hierarchy))
        self.assertRegex(combined, r"(?is)separate mutable.*surface.*visible senior")
        self.assertRegex(combined, r"(?is)hidden.*subagent.*bounded sidecar")
        self.assertRegex(combined, r"(?is)small.*single.surface.*subagent|bounded small.*subagent")
        self.assertRegex(combined, r"(?is)cannot.*(?:own|accept|hand off).*lane")


if __name__ == "__main__":
    unittest.main()
