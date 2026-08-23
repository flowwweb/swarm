from __future__ import annotations

from dataclasses import replace
import unittest

from skills.swarm.runtime import (
    InvariantError,
    LaneMaterialization,
    ProfessionAssignment,
    Role,
    TopologyMaterializationPlan,
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
        with self.assertRaisesRegex(InvariantError, "leaf LEAD"):
            TopologyMaterializationPlan((self.ctrl(), self.lead()))

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
