from __future__ import annotations

import unittest
import skills.swarm.runtime.core as runtime_core

from skills.swarm.runtime import (
    AcceptanceContract,
    CtrlOperation,
    HostUserEvent,
    InvariantError,
    LaneKind,
    Role,
    SubagentException,
    Swarm,
    Task,
)
from skills.swarm.runtime.core import _sha256_text


class CtrlAuthorityGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.swarm,self.host=Swarm.with_host_authority()
        ctrl=Task("ctrl-a","CTRL","CTRL",1,{},risk=1,subagent_exception=SubagentException.WHOLE_TASK_COST,subagent_exception_reason="direct control record",lane_kind=LaneKind.NON_CODE,acceptance_contract=AcceptanceContract.empty())
        self.swarm.start_ctrl_direct(Role.CTRL,ctrl,outcomes=1,mutable_surfaces=1,cross_lane_dependency=False,measurable_minutes=1)

    def authorization(self, operation:CtrlOperation=CtrlOperation.CREATE, *, target:str="ctrl-b", objective:str="objective-b"):
        user_receipt=f"usr-{operation.value.lower()}-decision000"
        event=self.host.mint_user_event(receipt=user_receipt,operation=operation,source_ctrl_id="ctrl-a",target_objective_digest=_sha256_text(objective),target_scope_digest=_sha256_text(target),target_identity=target,issued_at=1,host_event_digest=_sha256_text(f"host:{operation.value}:{target}:{objective}"))
        return self.swarm.record_user_ctrl_authorization(Role.CTRL,event)

    def test_ctrl_cannot_extract_host_mint_authority_from_swarm(self) -> None:
        self.assertFalse(hasattr(self.swarm,"_host_user_event_capability"))
        self.assertFalse(hasattr(self.swarm,"_external_proof_capability"))
        self.assertFalse(hasattr(runtime_core,"_HOST_AUTHORITY_BROKERS"))
        self.assertFalse(hasattr(runtime_core,"_registered_host_broker"))
        with self.assertRaises(AttributeError): getattr(self.swarm,"_host_user_event_capability")
        with self.assertRaises(AttributeError): getattr(self.swarm,"_ingest_host_user_event")

    def test_public_verifier_cannot_mint_user_authority(self) -> None:
        forged=HostUserEvent("usr-public-key-forgery000",CtrlOperation.CREATE,"ctrl-a",_sha256_text("objective-b"),_sha256_text("ctrl-b"),"ctrl-b",1,_sha256_text("forged-public-key"))
        with self.assertRaisesRegex(InvariantError,"host-validated user authorization"):
            self.swarm.record_user_ctrl_authorization(Role.CTRL,forged)

    def test_ctrl_cannot_replace_or_clear_the_host_verifier(self) -> None:
        attacker_private=7
        attacker_public=pow(runtime_core._HOST_AUTHORITY_GENERATOR,attacker_private,runtime_core._HOST_AUTHORITY_PRIME)
        with self.assertRaisesRegex(InvariantError,"verifier is immutable"):
            self.swarm._host_authority_public_key=attacker_public
        with self.assertRaisesRegex(InvariantError,"verifier is immutable"):
            self.swarm._host_authority_public_key=None

    def test_host_signature_cannot_be_replayed_for_a_changed_objective(self) -> None:
        signed=self.host.mint_user_event(receipt="usr-signed-binding000",operation=CtrlOperation.CREATE,source_ctrl_id="ctrl-a",target_objective_digest=_sha256_text("objective-b"),target_scope_digest=_sha256_text("ctrl-b"),target_identity="ctrl-b",issued_at=1,host_event_digest=_sha256_text("signed-binding"))
        changed=HostUserEvent(signed.receipt,signed.operation,signed.source_ctrl_id,_sha256_text("objective-c"),signed.target_scope_digest,signed.target_identity,signed.issued_at,signed.event_digest)
        object.__setattr__(changed,"_signature",signed._signature)
        with self.assertRaisesRegex(InvariantError,"host-validated user authorization"):
            self.swarm.record_user_ctrl_authorization(Role.CTRL,changed)

    def test_ctrl_cannot_self_mint_user_authority_from_feed_receipts(self) -> None:
        forged=HostUserEvent("usr-forged-decision000",CtrlOperation.CREATE,"ctrl-a",_sha256_text("objective-b"),_sha256_text("ctrl-b"),"ctrl-b",1,_sha256_text("forged"))
        with self.assertRaisesRegex(InvariantError,"host-validated user authorization"):
            self.swarm.record_user_ctrl_authorization(Role.CTRL,forged)

    def test_exact_authorization_emits_one_consumable_intent(self) -> None:
        authorization=self.authorization()
        intent=self.swarm.plan_ctrl_materialization(Role.CTRL,authorization,operation=CtrlOperation.CREATE,source_ctrl_id="ctrl-a",target_objective_digest=_sha256_text("objective-b"),target_scope_digest=_sha256_text("ctrl-b"),target_identity="ctrl-b")
        self.assertEqual(self.swarm.consume_ctrl_materialization_intent(intent),intent.intent_digest)
        with self.assertRaisesRegex(InvariantError,"replayed"):
            self.swarm.consume_ctrl_materialization_intent(intent)

    def test_missing_mismatched_and_cross_operation_authority_fail_closed(self) -> None:
        with self.assertRaisesRegex(InvariantError,"HUMAN_AUTHORITY_BLOCKER"):
            self.swarm.plan_ctrl_materialization(Role.CTRL,None,operation=CtrlOperation.CREATE,source_ctrl_id="ctrl-a",target_objective_digest=_sha256_text("objective-b"),target_scope_digest=_sha256_text("ctrl-b"),target_identity="ctrl-b")
        authorization=self.authorization(CtrlOperation.FORK)
        with self.assertRaisesRegex(InvariantError,"HUMAN_AUTHORITY_BLOCKER"):
            self.swarm.plan_ctrl_materialization(Role.CTRL,authorization,operation=CtrlOperation.REPLACE,source_ctrl_id="ctrl-a",target_objective_digest=_sha256_text("objective-b"),target_scope_digest=_sha256_text("ctrl-b"),target_identity="ctrl-b")

    def test_recovery_allows_same_identity_but_not_replacement(self) -> None:
        self.assertEqual(self.swarm.restore_same_ctrl_identity(Role.CTRL,"ctrl-a","ctrl-a",provenance_receipt="evt-restore-same000"),"evt-restore-same000")
        with self.assertRaisesRegex(InvariantError,"RECOVER_AS_NEW"):
            self.swarm.restore_same_ctrl_identity(Role.CTRL,"ctrl-a","ctrl-b",provenance_receipt="evt-restore-new000")

    def test_successor_requires_exact_user_authorization(self) -> None:
        self.swarm.tasks["successor"]=Task("successor","CTRL","CTRL",1,{},goal_id="goal-b",lane_kind=LaneKind.NON_CODE,acceptance_contract=AcceptanceContract.empty())
        self.swarm.tasks["ctrl-a"].goal_id="goal-a"
        with self.assertRaisesRegex(InvariantError,"HUMAN_AUTHORITY_BLOCKER"):
            self.swarm.link_successor(Role.CTRL,"ctrl-a","successor")
        authorization=self.authorization(CtrlOperation.SUCCESSOR,target="successor",objective="goal-b")
        self.swarm.link_successor(Role.CTRL,"ctrl-a","successor",authorization=authorization)
        self.assertEqual(self.swarm.tasks["successor"].milestone_history[-1][1],"SUCCESSOR")

    def test_requested_specialists_do_not_require_ctrl_authorization(self) -> None:
        self.swarm.specialist_event(Role.SPECIALIST,"ctrl-a",specialist_id="researcher",profession="RESEARCHER",goal_id="research",accepted_change="cost report",invalidates_map=False,receipt="research-pass")
        self.swarm.specialist_event(Role.SPECIALIST,"ctrl-a",specialist_id="architect",profession="ARCHITECT",goal_id="architecture",accepted_change="lean plan",invalidates_map=False,receipt="architecture-pass")
        self.assertEqual(self.swarm.tasks["ctrl-a"].specialist_professions,{"researcher":"RESEARCHER","architect":"ARCHITECT"})


if __name__ == "__main__":
    unittest.main()
