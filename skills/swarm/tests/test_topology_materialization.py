from __future__ import annotations

from dataclasses import replace
import unittest

from skills.swarm.runtime import (
    InvariantError,
    LaneMaterialization,
    ProfessionAssignment,
    Role,
    SubordinateBoundaryFacts,
    TopologyDispatchPreflight,
    TopologyHostCapability,
    TopologyMaterializationPlan,
    TopologyTransportOutcome,
)


class TopologyMaterializationTests(unittest.TestCase):
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
        packet = TopologyDispatchPreflight().prepare(plan, ready_lane_ids=("data",))
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
        preflight = TopologyDispatchPreflight()
        producer_wave = preflight.prepare(plan, ready_lane_ids=("adapter",))
        self.assertEqual(tuple(lane.lane_id for lane in producer_wave.lanes), ("adapter",))
        with self.assertRaisesRegex(InvariantError, "before.*producer artifact is frozen"):
            preflight.prepare(plan, ready_lane_ids=("review",))
        review_wave = preflight.prepare(plan, ready_lane_ids=("review",), frozen_artifact_ids=("codex-adapter",))
        self.assertEqual(tuple(lane.lane_id for lane in review_wave.lanes), ("review",))

    def test_pending_lane_reservation_blocks_schema_retry_until_resolution_or_cancel(self) -> None:
        plan = TopologyMaterializationPlan((self.ctrl(), self.doer(parent="ctrl")))
        packet = TopologyDispatchPreflight().prepare(plan, ready_lane_ids=("adapter",))
        for outcome in (TopologyTransportOutcome.FAILED, TopologyTransportOutcome.AMBIGUOUS):
            with self.subTest(outcome=outcome):
                preflight = TopologyDispatchPreflight()
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
