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

    def test_step_zero_and_lifecycle_never_authorize_automatic_pinning(self):
        root = Path(__file__).parents[1]
        skill = (root / "SKILL.md").read_text(encoding="utf-8")
        task_contract = (root / "references" / "task-contract.md").read_text(encoding="utf-8")
        skill_step_zero = skill.split("**Step 0, never defer:**", 1)[1].split("\n\n", 1)[0]
        task_step_zero = task_contract.split("Step 0 first:", 1)[1].split("\n\n", 1)[0]
        for step_zero in (skill_step_zero, task_step_zero):
            self.assertRegex(step_zero, r"(?is)fresh host-owned custody receipt")
            self.assertRegex(step_zero, r"(?is)SWARM.*never.*(?:calls|requests|authorizes).*pin")
            self.assertRegex(step_zero, r"(?is)pinned: false.*placement(?:_status)?: placement_unverified")
            self.assertRegex(step_zero, r"(?is)only (?:the |direct )?host.*exact.*explicit-user.*(?:pin )?request")
            self.assertRegex(step_zero, r"(?is)otherwise preserve.*user state")
        combined = "\n".join((skill, task_contract))
        for forbidden in ("AUTO_PIN", "TEMPORARY_REVIEW_PIN", "concrete ready-review handoff"):
            self.assertNotIn(forbidden, combined)

    def test_direct_user_ctrl_keep_out_is_scoped_and_releasable(self):
        root = Path(__file__).parents[1]
        combined = "\n".join(
            (root / path).read_text(encoding="utf-8")
            for path in ("SKILL.md", "references/hierarchy.md", "references/monitoring.md")
        )
        self.assertRegex(combined, r"(?is)fresh host-observed direct-user turn.*scoped.*keep-out")
        self.assertRegex(combined, r"(?is)must not.*conflicting.*duplicate.*enqueue follow-ups.*wake.*interrupt")
        self.assertRegex(combined, r"(?is)unaffected.*lanes.*read-only.*(?:heartbeat|observation)")
        self.assertRegex(combined, r"(?is)turn completes.*explicit.*hand(?:s|ed)?\s*(?:coordination\s*)?back.*release")
        self.assertRegex(combined, r"(?is)(?:silence|stale).*cannot.*indefinitely")
        self.assertRegex(combined, r"(?is)user actions always win")

    def test_instruction_changes_are_scoped_instead_of_overcorrected(self):
        root = Path(__file__).parents[1]
        combined = "\n".join(
            (root / path).read_text(encoding="utf-8")
            for path in ("SKILL.md", "references/hierarchy.md", "references/task-contract.md")
        )
        self.assertRegex(combined, r"(?is)steer, do not overcorrect")
        self.assertRegex(combined, r"(?is)ADDITIVE.*CORRECTIVE.*REVERSAL")
        self.assertRegex(combined, r"(?is)explicitly named scope.*accepted behavior.*preserv")
        self.assertRegex(combined, r"(?is)CORRECTIVE.*smallest coherent adjustment")
        self.assertRegex(combined, r"(?is)REVERSAL.*only the explicitly reversed behavior")
        self.assertRegex(combined, r"(?is)local correction.*(?:never implies|never turn).*blanket.*(?:rule|opposite)")
        self.assertRegex(combined, r"(?is)topology.*dirty custody.*proof boundaries.*(?:unaffected|unrelated).*lanes")

    def test_long_lived_checkpoint_handoff_and_archive_are_evidence_gated(self):
        root = Path(__file__).parents[1]
        combined = "\n".join(
            (root / path).read_text(encoding="utf-8")
            for path in ("SKILL.md", "references/hierarchy.md", "references/task-contract.md", "references/monitoring.md")
        )
        self.assertRegex(combined, r"(?is)meaningful stable (?:boundary|checkpoint).*task identity.*state.*SHA/tree/parent")
        self.assertRegex(combined, r"(?is)dirty custody.*proof manifest.*claim limits.*blocker.*next bounded action")
        self.assertRegex(combined, r"(?is)coherent attributable.*proportionate proof")
        self.assertRegex(combined, r"(?is)never automatically stage.*reset.*clean.*commit.*unrelated dirty work")
        self.assertRegex(combined, r"(?is)successor.*acknowledges.*exact.*immutable checkpoint")
        self.assertRegex(combined, r"(?is)creation age alone.*never.*stale|age alone is never stale")
        self.assertRegex(combined, r"(?is)no active process.*file handle.*lock")
        self.assertRegex(combined, r"(?is)size stability across bounded observations")
        self.assertRegex(combined, r"(?is)file count.*byte count.*hash parity.*recoverable manifest")
        self.assertRegex(combined, r"(?is)active or growing logs.*protected")

    def test_resource_pressure_is_command_scoped_not_a_project_freeze(self):
        root = Path(__file__).parents[1]
        combined = "\n".join(
            (root / path).read_text(encoding="utf-8")
            for path in ("SKILL.md", "references/monitoring.md")
        )
        self.assertRegex(combined, r"(?is)resource pressure is command-scoped, not a (?:lane-wide|project) freeze")
        self.assertRegex(combined, r"(?is)above the exact.*critical safety floor.*source.*review.*small durable checkpoints")
        self.assertRegex(combined, r"(?is)serialize only predictably large build.*export.*browser.*Docker.*install.*device.*provider")
        self.assertIn("`O:\\`", combined)
        self.assertRegex(combined, r"(?is)large sequential artifacts.*immutable evidence.*archives.*installers.*release bundles")
        self.assertRegex(combined, r"(?is)active worktrees.*databases.*dependency trees.*random-I/O-heavy caches.*local")
        self.assertRegex(combined, r"(?is)10 GiB.*not.*freeze gate")
        self.assertRegex(combined, r"(?is)stale or rebuildable residue.*(?:incrementally|bounded\s+increments).*free space")
        self.assertRegex(combined, r"(?is)never\s+touches active or\s+growing logs.*current sessions.*databases.*dirty product work")
        self.assertRegex(combined, r"(?is)live[-\s]+process(?:-referenced|.*paths referenced)")

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
