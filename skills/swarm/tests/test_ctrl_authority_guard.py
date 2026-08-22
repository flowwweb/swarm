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
        self.swarm=Swarm()
        ctrl=Task("ctrl-a","CTRL","CTRL",1,{},risk=1,subagent_exception=SubagentException.WHOLE_TASK_COST,subagent_exception_reason="direct control record",lane_kind=LaneKind.NON_CODE,acceptance_contract=AcceptanceContract.empty())
        self.swarm.start_ctrl_direct(Role.CTRL,ctrl,outcomes=1,mutable_surfaces=1,cross_lane_dependency=False,measurable_minutes=1)

    def test_ctrl_cannot_extract_host_mint_authority_from_swarm(self) -> None:
        self.assertFalse(hasattr(Swarm,"with_host_authority"))
        self.assertFalse(hasattr(Swarm,"from_config_with_host_authority"))
        self.assertFalse(hasattr(self.swarm,"mint_user_event"))
        self.assertFalse(hasattr(runtime_core,"_HostAuthorityBroker"))
        self.assertFalse(hasattr(runtime_core,"_HOST_ADAPTER_SEAL"))
        self.assertFalse(hasattr(runtime_core,"_authority_sign"))
        self.assertFalse(hasattr(runtime_core,"HostReceiptVerifier"))
        self.assertFalse(hasattr(Swarm,"_with_host_verifier"))

    def test_missing_external_trust_root_fails_closed(self) -> None:
        event=HostUserEvent("usr-no-root000",CtrlOperation.CREATE,"ctrl-a",_sha256_text("objective-b"),_sha256_text("ctrl-b"),"ctrl-b",1,_sha256_text("no-root"))
        with self.assertRaisesRegex(InvariantError,"no host-pinned trust root or IPC verifier"):
            self.swarm.record_user_ctrl_authorization(Role.CTRL,event)

    def test_public_verifier_cannot_mint_user_authority(self) -> None:
        forged=HostUserEvent("usr-public-key-forgery000",CtrlOperation.CREATE,"ctrl-a",_sha256_text("objective-b"),_sha256_text("ctrl-b"),"ctrl-b",1,_sha256_text("forged-public-key"))
        with self.assertRaisesRegex(InvariantError,"no host-pinned trust root or IPC verifier"):
            self.swarm.record_user_ctrl_authorization(Role.CTRL,forged)

    def test_ctrl_cannot_replace_or_clear_the_host_verifier(self) -> None:
        self.assertFalse(hasattr(self.swarm,"_host_receipt_verifier"))

    def test_self_minted_event_is_rejected_without_the_sealed_host_adapter(self) -> None:
        event=HostUserEvent("usr-self-minted000",CtrlOperation.CREATE,"ctrl-a",_sha256_text("objective-b"),_sha256_text("ctrl-b"),"ctrl-b",1,_sha256_text("self-minted"))
        with self.assertRaisesRegex(InvariantError,"no host-pinned trust root or IPC verifier"):
            self.swarm.record_user_ctrl_authorization(Role.CTRL,event)

    def test_groom_rejects_missing_or_conflicting_archive_custody(self) -> None:
        task=self.swarm.tasks["ctrl-a"]; task.state=runtime_core.TaskState.COMPLETE; task.completed_at=0
        with self.assertRaisesRegex(InvariantError,"no host-pinned trust root or IPC verifier"):
            self.swarm.groom(Role.CTRL,5,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1})
        self.assertEqual(task.state,runtime_core.TaskState.COMPLETE)
        with self.assertRaisesRegex(InvariantError,"no host-pinned trust root or IPC verifier"):
            self.swarm.record_host_custody_receipt(Role.CTRL,None)
        with self.assertRaisesRegex(InvariantError,"no host-pinned trust root or IPC verifier"):
            self.swarm.groom(Role.CTRL,5,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1})
        self.assertEqual(task.state,runtime_core.TaskState.COMPLETE)

    def test_groom_accepts_only_fresh_exact_archive_custody_and_blocks_user_pin(self) -> None:
        task=self.swarm.tasks["ctrl-a"]; task.state=runtime_core.TaskState.COMPLETE; task.completed_at=0
        with self.assertRaisesRegex(InvariantError,"no host-pinned trust root or IPC verifier"):
            self.swarm.record_host_custody_receipt(Role.CTRL,None)
        with self.assertRaisesRegex(InvariantError,"no host-pinned trust root or IPC verifier"):
            self.swarm.groom(Role.CTRL,5,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1})
        self.assertEqual(task.state,runtime_core.TaskState.COMPLETE)
        task.user_pinned=True
        with self.assertRaisesRegex(InvariantError,"user-renamed or user-pinned"):
            self.swarm.groom(Role.CTRL,5,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1})

    def test_host_signature_cannot_be_replayed_for_a_changed_objective(self) -> None:
        changed=HostUserEvent("usr-signed-binding000",CtrlOperation.CREATE,"ctrl-a",_sha256_text("objective-c"),_sha256_text("ctrl-b"),"ctrl-b",1,_sha256_text("signed-binding"))
        with self.assertRaisesRegex(InvariantError,"no host-pinned trust root or IPC verifier"):
            self.swarm.record_user_ctrl_authorization(Role.CTRL,changed)

    def test_ctrl_cannot_self_mint_user_authority_from_feed_receipts(self) -> None:
        forged=HostUserEvent("usr-forged-decision000",CtrlOperation.CREATE,"ctrl-a",_sha256_text("objective-b"),_sha256_text("ctrl-b"),"ctrl-b",1,_sha256_text("forged"))
        with self.assertRaisesRegex(InvariantError,"no host-pinned trust root or IPC verifier"):
            self.swarm.record_user_ctrl_authorization(Role.CTRL,forged)

    def test_exact_authorization_emits_only_a_non_authoritative_request(self) -> None:
        event=HostUserEvent("usr-no-authority000",CtrlOperation.CREATE,"ctrl-a",_sha256_text("objective-b"),_sha256_text("ctrl-b"),"ctrl-b",1,_sha256_text("no-authority"))
        with self.assertRaisesRegex(InvariantError,"no host-pinned trust root or IPC verifier"):
            self.swarm.record_user_ctrl_authorization(Role.CTRL,event)

    def test_missing_mismatched_and_cross_operation_authority_fail_closed(self) -> None:
        with self.assertRaisesRegex(InvariantError,"HUMAN_AUTHORITY_BLOCKER"):
            self.swarm.plan_ctrl_materialization(Role.CTRL,None,operation=CtrlOperation.CREATE,source_ctrl_id="ctrl-a",target_objective_digest=_sha256_text("objective-b"),target_scope_digest=_sha256_text("ctrl-b"),target_identity="ctrl-b")
        authorization=runtime_core.UserCtrlAuthorization("usr-fork-forged000",CtrlOperation.FORK,"ctrl-a",_sha256_text("objective-b"),_sha256_text("ctrl-b"),"ctrl-b",1,_sha256_text("forged"))
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
        authorization=runtime_core.UserCtrlAuthorization("usr-successor000",CtrlOperation.SUCCESSOR,"ctrl-a",_sha256_text("goal-b"),_sha256_text("successor"),"successor",1,_sha256_text("forged"))
        with self.assertRaisesRegex(InvariantError,"HUMAN_AUTHORITY_BLOCKER"):
            self.swarm.link_successor(Role.CTRL,"ctrl-a","successor",authorization=authorization)
        self.assertEqual(self.swarm.tasks["successor"].milestone_history,[])

    def test_requested_specialists_do_not_require_ctrl_authorization(self) -> None:
        self.swarm.specialist_event(Role.SPECIALIST,"ctrl-a",specialist_id="researcher",profession="RESEARCHER",goal_id="research",accepted_change="cost report",invalidates_map=False,receipt="research-pass")
        self.swarm.specialist_event(Role.SPECIALIST,"ctrl-a",specialist_id="architect",profession="ARCHITECT",goal_id="architecture",accepted_change="lean plan",invalidates_map=False,receipt="architecture-pass")
        self.assertEqual(self.swarm.tasks["ctrl-a"].specialist_professions,{"researcher":"RESEARCHER","architect":"ARCHITECT"})


if __name__ == "__main__":
    unittest.main()
