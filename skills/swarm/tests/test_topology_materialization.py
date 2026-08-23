from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest

from skills.swarm.runtime import (
    AcceptanceContract,
    ArtifactIdentity,
    CtrlMode,
    IncidentLedger,
    InvariantError,
    LaneMaterialization,
    LaneKind,
    ProfessionAssignment,
    ProofState,
    ReviewEvidence,
    ReviewScope,
    ReviewStrategy,
    Role,
    SubordinateBoundaryFacts,
    Swarm,
    Task,
    TopologyArtifactFreezeReceipt,
    TopologyDispatchPreflight,
    TopologyHostCapability,
    TopologyMaterializationPlan,
    TopologyTransportOutcome,
    Worker,
)


class TopologyMaterializationTests(unittest.TestCase):
    def preflight(self, swarm: Swarm | None = None) -> TopologyDispatchPreflight:
        return (swarm or Swarm()).topology_dispatch_preflight("ctrl", "thread-ctrl")

    def ctrl(self) -> LaneMaterialization:
        return LaneMaterialization("ctrl", Role.CTRL, "Ship the SWARM release", icon="🐙")

    def lead(self, lane_id="runtime", parent="ctrl", *, direct=False) -> LaneMaterialization:
        return LaneMaterialization(
            lane_id,
            Role.LEAD,
            "Runtime policy",
            parent,
            ProfessionAssignment("architect"),
            "🏛️",
            "skills/swarm/runtime",
            "runtime-policy" if direct else "",
            direct_production=direct,
            durable_boundary=None if direct else SubordinateBoundaryFacts(integration_review_surface=True),
        )

    def doer(self, lane_id="adapter", parent="runtime", artifact="codex-adapter", profession="developer") -> LaneMaterialization:
        return LaneMaterialization(
            lane_id,
            Role.DOER,
            "Codex adapter",
            parent,
            ProfessionAssignment(profession),
            "💻",
            artifact_id=artifact,
            direct_production=True,
        )

    def test_one_ctrl_admin_and_profession_plus_structural_role_are_visible_in_titles(self) -> None:
        reviewer = LaneMaterialization(
            "review",
            Role.DOER,
            "Exact candidate",
            "runtime",
            ProfessionAssignment("reviewer"),
            "🔎",
            artifact_id="review-receipt",
            review_target_id="adapter",
            direct_production=True,
        )
        plan = TopologyMaterializationPlan((self.ctrl(), self.lead(), self.doer(), reviewer))
        self.assertEqual(plan.lanes[0].title, "🐙CTRL - Ship the SWARM release")
        self.assertEqual(plan.lanes[1].title, "🏛️Architect LEAD - Runtime policy")
        self.assertEqual(plan.lanes[2].title, "💻Dev DOER - Codex adapter")
        self.assertEqual(plan.lanes[3].title, "🔎Reviewer DOER - Exact candidate")
        self.assertEqual(len(plan.plan_digest), 64)
        self.assertEqual(sum(lane.structural_role is Role.CTRL for lane in plan.lanes), 1)

    def test_lead_may_produce_directly_but_empty_leaf_lead_is_rejected(self) -> None:
        direct = TopologyMaterializationPlan((self.ctrl(), self.lead(direct=True)))
        self.assertTrue(direct.lanes[1].direct_production)
        with self.assertRaisesRegex(InvariantError, "durable-boundary evidence"):
            LaneMaterialization(
                "empty-lead",
                Role.LEAD,
                "Unjustified lane",
                "ctrl",
                ProfessionAssignment("manager"),
                "🧭",
                "empty-boundary",
            )

    def test_helm_style_bare_or_profession_only_titles_and_lead_roster_fail_closed(self) -> None:
        for title in ("LEAD - product", "DESIGNER", "REVIEW"):
            with self.subTest(title=title), self.assertRaisesRegex(InvariantError, "generated icon, profession"):
                LaneMaterialization(
                    "product",
                    Role.DOER,
                    "Product brief",
                    "ctrl",
                    ProfessionAssignment("manager"),
                    "🧭",
                    artifact_id="product-brief",
                    direct_production=True,
                    requested_title=title,
                )
        with self.assertRaisesRegex(InvariantError, "durable-boundary evidence"):
            LaneMaterialization(
                "data",
                Role.LEAD,
                "Data artifact",
                "ctrl",
                ProfessionAssignment("analyst"),
                "📊",
                "data.py",
            )
        bounded = self.doer("data", parent="ctrl", artifact="data.py", profession="analyst")
        self.assertEqual((bounded.structural_role, bounded.title), (Role.DOER, "💻Analyst DOER - Codex adapter"))

    def test_typed_durable_nested_lead_is_valid_in_the_current_ready_wave(self) -> None:
        nested = LaneMaterialization(
            "data",
            Role.LEAD,
            "Data boundary",
            "ctrl",
            ProfessionAssignment("analyst"),
            "📊",
            "src/data",
            durable_boundary=SubordinateBoundaryFacts(heartbeat_obligation=True, worktree_isolation=True),
            requested_title="📊Analyst LEAD - Data boundary",
        )
        plan = TopologyMaterializationPlan((self.ctrl(), nested))
        packet = self.preflight().prepare(plan, ready_lane_ids=("data",))
        self.assertEqual(packet.host_capability, TopologyHostCapability.INSTRUCTION_ONLY_UNSUPPORTED)
        self.assertEqual(tuple(lane.lane_id for lane in packet.lanes), ("data",))

    def test_current_ready_wave_defers_review_until_the_producer_artifact_is_frozen(self) -> None:
        producer = self.doer("adapter", parent="ctrl", artifact="codex-adapter")
        reviewer = LaneMaterialization(
            "review",
            Role.DOER,
            "Exact candidate",
            "ctrl",
            ProfessionAssignment("reviewer"),
            "🔎",
            artifact_id="review-receipt",
            review_target_id="adapter",
            direct_production=True,
        )
        plan = TopologyMaterializationPlan((self.ctrl(), producer, reviewer))
        preflight = self.preflight()
        producer_wave = preflight.prepare(plan, ready_lane_ids=("adapter",))
        self.assertEqual(tuple(lane.lane_id for lane in producer_wave.lanes), ("adapter",))
        with self.assertRaisesRegex(InvariantError, "artifact freeze receipt"):
            preflight.prepare(plan, ready_lane_ids=("review",))

    def test_runtime_accepted_content_addressed_freeze_enables_exact_review_lane(self) -> None:
        producer = self.doer("adapter", parent="ctrl", artifact="codex-adapter")
        reviewer = LaneMaterialization(
            "review", Role.DOER, "Exact candidate", "ctrl", ProfessionAssignment("reviewer"), "🔎",
            artifact_id="review-receipt", review_target_id="adapter", direct_production=True,
        )
        plan = TopologyMaterializationPlan((self.ctrl(), producer, reviewer))
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "artifact.txt"
            path.write_text("frozen", encoding="utf-8")
            artifact = ArtifactIdentity.capture("codex-adapter", "rev-1", "candidate", root=root, paths=("artifact.txt",))
            swarm = Swarm()
            swarm.add_lead(Role.CTRL, "lead")
            swarm.add_worker(Role.LEAD, Worker("builder", "lead", 1))
            task = Task(
                "adapter", "builder", "author", 1, {}, subagent_receipt="host:thread:adapter",
                ctrl_mode=CtrlMode.DIRECT, lane_kind=LaneKind.CODE, owning_lead_id="lead",
                acceptance_contract=AcceptanceContract(artifact, ("freeze-gate",), observation_root=root),
            )
            swarm.assign(Role.LEAD, task)
            swarm.consult_incidents(Role.LEAD, "adapter", IncidentLedger(root), artifact="codex-adapter", scope="topology", actor_id="lead")
            swarm.run_gate(Role.LEAD, "adapter", "freeze-gate", (sys.executable, "-c", "pass"), cwd=root, actor_id="lead")
            review = ReviewEvidence(
                ReviewStrategy.LIGHT, "review-owner", True, artifact,
                receipt=(("acceptance", "review:adapter"),), scope=ReviewScope.ACCEPTANCE,
                plan_digest=task.acceptance_contract.proof_plan.plan_digest,
            )
            task.review_passed = True
            task.reviewer = review.reviewer
            task.acceptance_review_receipt = review
            self.assertEqual(swarm.proof_state("adapter"), ProofState.ACCEPTANCE_REVIEW)
            with self.assertRaisesRegex(InvariantError, "runtime-issued exact-artifact independent acceptance"):
                swarm.issue_topology_artifact_freeze("adapter", "review", plan.plan_digest)
            task.review_passed = False
            task.reviewer = None
            task.acceptance_review_receipt = None

            rejected_reviews = (
                replace(review, independent=False),
                replace(review, reviewer="builder"),
                replace(review, artifact=ArtifactIdentity("wrong", "rev-1", "candidate")),
                replace(review, plan_digest="0" * 64),
            )
            for rejected in rejected_reviews:
                with self.subTest(rejected=rejected), self.assertRaises(InvariantError):
                    swarm.review(Role.REVIEW, "adapter", rejected, True)
            swarm.review(Role.REVIEW, "adapter", review, True)
            self.assertEqual(swarm.proof_state("adapter"), ProofState.ACCEPTED)
            issued_acceptance = swarm._runtime_acceptances.get("adapter")
            self.assertIsNotNone(issued_acceptance)
            swarm._runtime_acceptances["adapter"] = replace(issued_acceptance)
            self.assertEqual(swarm.proof_state("adapter"), ProofState.ACCEPTANCE_REVIEW)
            with self.assertRaisesRegex(InvariantError, "runtime-issued exact-artifact independent acceptance"):
                swarm.issue_topology_artifact_freeze("adapter", "review", plan.plan_digest)
            swarm._runtime_acceptances["adapter"] = issued_acceptance
            freeze = swarm.issue_topology_artifact_freeze("adapter", "review", plan.plan_digest)
            preflight = self.preflight(swarm)
            packet = preflight.prepare(plan, ready_lane_ids=("review",), artifact_freeze_receipts=(freeze,))
            self.assertEqual(tuple(lane.lane_id for lane in packet.lanes), ("review",))
            with self.assertRaisesRegex(InvariantError, "typed runtime-issued"):
                preflight.prepare(plan, ready_lane_ids=("review",), artifact_freeze_receipts=("codex-adapter",))
            forged = replace(freeze)
            with self.assertRaisesRegex(InvariantError, "untrusted"):
                preflight.prepare(plan, ready_lane_ids=("review",), artifact_freeze_receipts=(forged,))
            with self.assertRaisesRegex(InvariantError, "artifact content"):
                replace(freeze, artifact_content_digest="")
            with self.assertRaisesRegex(InvariantError, "content-observed"):
                TopologyArtifactFreezeReceipt("adapter", "review", plan.plan_digest, ArtifactIdentity("codex-adapter", "mutable", "candidate"), "0" * 64, freeze.proof_plan_digest, freeze.review_receipt_digest, freeze.gate_receipt_digests, freeze.state, 1000, 1001, freeze.claim_limit)
            with self.assertRaisesRegex(InvariantError, "producer/plan/review"):
                wrong_plan = swarm.issue_topology_artifact_freeze("adapter", "review", "0" * 64)
                preflight.prepare(plan, ready_lane_ids=("review",), artifact_freeze_receipts=(wrong_plan,))
            with self.assertRaisesRegex(InvariantError, "producer/plan/review"):
                wrong_review = swarm.issue_topology_artifact_freeze("adapter", "other-review", plan.plan_digest)
                preflight.prepare(plan, ready_lane_ids=("review",), artifact_freeze_receipts=(wrong_review,))
            other = self.doer("other", parent="ctrl", artifact="other-artifact")
            other_review = replace(reviewer, review_target_id="other")
            other_plan = TopologyMaterializationPlan((self.ctrl(), other, other_review))
            wrong_producer = swarm.issue_topology_artifact_freeze("adapter", "review", other_plan.plan_digest)
            with self.assertRaisesRegex(InvariantError, "producer/plan/review"):
                preflight.prepare(other_plan, ready_lane_ids=("review",), artifact_freeze_receipts=(wrong_producer,))
            valid_until = freeze.valid_until_ms
            object.__setattr__(freeze, "valid_until_ms", freeze.observed_at_ms - 1)
            with self.assertRaisesRegex(InvariantError, "untrusted, stale, rejected"):
                preflight.prepare(plan, ready_lane_ids=("review",), artifact_freeze_receipts=(freeze,))
            object.__setattr__(freeze, "valid_until_ms", valid_until)
            for changed_review in (
                replace(review, independent=False),
                replace(review, reviewer="builder"),
                replace(review, artifact=ArtifactIdentity("wrong", "rev-1", "candidate")),
                replace(review, plan_digest="0" * 64),
            ):
                with self.subTest(changed_review=changed_review):
                    task.acceptance_review_receipt = changed_review
                    task.reviewer = changed_review.reviewer
                    self.assertEqual(swarm.proof_state("adapter"), ProofState.ACCEPTANCE_REVIEW)
                    with self.assertRaisesRegex(InvariantError, "runtime-issued exact-artifact independent acceptance"):
                        swarm.issue_topology_artifact_freeze("adapter", "review", plan.plan_digest)
            task.acceptance_review_receipt = review
            task.reviewer = review.reviewer
            original_owner = task.owner
            task.owner = review.reviewer
            self.assertEqual(swarm.proof_state("adapter"), ProofState.ACCEPTANCE_REVIEW)
            task.owner = original_owner
            original_contract = task.acceptance_contract
            task.acceptance_contract = AcceptanceContract(artifact, ("changed-plan",), observation_root=root)
            self.assertNotEqual(swarm.proof_state("adapter"), ProofState.ACCEPTED)
            task.acceptance_contract = original_contract
            path.write_text("changed", encoding="utf-8")
            self.assertNotEqual(swarm.proof_state("adapter"), ProofState.ACCEPTED)
            path.write_text("frozen", encoding="utf-8")
            self.assertEqual(swarm.proof_state("adapter"), ProofState.ACCEPTED)

    def test_child_dispatch_requires_previously_confirmed_parent_and_confirmation_is_retained(self) -> None:
        lead = self.lead("runtime", parent="ctrl")
        child = self.doer("adapter", parent="runtime")
        plan = TopologyMaterializationPlan((self.ctrl(), lead, child))
        preflight = self.preflight()
        with self.assertRaisesRegex(InvariantError, "parent must already be host-confirmed"):
            preflight.prepare(plan, ready_lane_ids=("runtime", "adapter"))
        lead_packet = preflight.prepare(plan, ready_lane_ids=("runtime",))
        lead_reservation = preflight.reserve(lead_packet)[0]
        preflight.record_transport(lead_reservation, TopologyTransportOutcome.CONFIRMED, host_task_id="thread-runtime")
        self.assertEqual(preflight.confirmed("runtime").host_task_id, "thread-runtime")
        child_packet = preflight.prepare(plan, ready_lane_ids=("adapter",))
        self.assertEqual(tuple(lane.lane_id for lane in child_packet.lanes), ("adapter",))
        with self.assertRaisesRegex(InvariantError, "already confirmed"):
            preflight.prepare(plan, ready_lane_ids=("runtime",))
        with self.assertRaisesRegex(InvariantError, "must resolve or be explicitly cancelled"):
            preflight.reserve(lead_packet)
        with self.assertRaisesRegex(InvariantError, "exact pending reservation"):
            preflight.cancel(lead_reservation)

    def test_pending_lane_reservation_blocks_schema_retry_until_resolution_or_cancel(self) -> None:
        plan = TopologyMaterializationPlan((self.ctrl(), self.doer(parent="ctrl")))
        packet = self.preflight().prepare(plan, ready_lane_ids=("adapter",))
        for outcome in (TopologyTransportOutcome.FAILED, TopologyTransportOutcome.AMBIGUOUS):
            with self.subTest(outcome=outcome):
                preflight = self.preflight()
                reservation = preflight.reserve(packet)[0]
                unresolved = preflight.record_transport(reservation, outcome)
                self.assertEqual(preflight.pending("adapter"), unresolved)
                with self.assertRaisesRegex(InvariantError, "must resolve or be explicitly cancelled"):
                    preflight.reserve(packet)
                preflight.cancel(unresolved)
                retry = preflight.reserve(packet)[0]
                confirmed = preflight.record_transport(retry, TopologyTransportOutcome.CONFIRMED, host_task_id="thread-1")
                self.assertEqual((confirmed.host_task_id, preflight.pending("adapter")), ("thread-1", None))

    def test_bounded_artifact_defaults_to_doer_and_doer_cannot_recruit_visible_lane(self) -> None:
        flat = TopologyMaterializationPlan((self.ctrl(), self.doer(parent="ctrl")))
        self.assertEqual(flat.lanes[1].structural_role, Role.DOER)
        child = replace(self.doer("child", parent="adapter", artifact="child-artifact"), responsibility="Child artifact")
        with self.assertRaisesRegex(InvariantError, "DOER.*cannot own"):
            TopologyMaterializationPlan((self.ctrl(), self.doer(parent="ctrl"), child))

    def test_large_root_fanout_requires_a_concrete_span_exception(self) -> None:
        leads = tuple(self.lead(f"lane-{index}", direct=True) for index in range(4))
        leads = tuple(
            replace(lane, mutable_boundary=f"boundary-{index}", artifact_id=f"artifact-{index}")
            for index, lane in enumerate(leads)
        )
        with self.assertRaisesRegex(InvariantError, "fanout exceeds"):
            TopologyMaterializationPlan((self.ctrl(), *leads), preferred_lane_width=3)
        accepted = TopologyMaterializationPlan(
            (self.ctrl(), *leads),
            preferred_lane_width=3,
            span_exception_receipt="topology:four-independent-boundaries",
        )
        self.assertEqual(len(accepted.lanes), 5)

    def test_review_cannot_target_itself_and_artifacts_have_one_owner(self) -> None:
        self_review = replace(
            self.doer("review", parent="ctrl", artifact="review-receipt", profession="reviewer"),
            review_target_id="review",
        )
        with self.assertRaisesRegex(InvariantError, "separate existing producer"):
            TopologyMaterializationPlan((self.ctrl(), self_review))
        duplicate = self.doer("second", parent="ctrl", artifact="codex-adapter")
        with self.assertRaisesRegex(InvariantError, "one visible accountable owner"):
            TopologyMaterializationPlan((self.ctrl(), self.doer(parent="ctrl"), duplicate))

    def test_nonstructural_roles_cannot_materialize_as_authority(self) -> None:
        with self.assertRaisesRegex(InvariantError, "exactly CTRL, LEAD, or DOER"):
            LaneMaterialization(
                "review",
                Role.REVIEW,
                "Review",
                "ctrl",
                ProfessionAssignment("reviewer"),
                "🔎",
                artifact_id="receipt",
                direct_production=True,
            )


if __name__ == "__main__":
    unittest.main()
