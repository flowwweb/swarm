from __future__ import annotations

import json
import unittest
from pathlib import Path

from skills.swarm.runtime.core import ArtifactIdentity, DelegationContract, ProofClass, Role, SubagentException, Swarm, Task


ROOT = Path(__file__).resolve().parents[1]


class InternalApprovalFallbackContractTests(unittest.TestCase):
    def test_local_access_requests_once_and_pending_approval_waits(self) -> None:
        skill = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in ("SKILL.md", "references/hierarchy.md"))
        hierarchy = (ROOT / "references" / "hierarchy.md").read_text(encoding="utf-8")
        recovery = (ROOT / "references" / "runtime-recovery.md").read_text(encoding="utf-8")
        hierarchy = " ".join(hierarchy.split())
        recovery = " ".join(recovery.split())

        self.assertRegex(skill, r"(?is)ordinary\s+local access failure.*requests supported sandbox or access\s+approval once.*Pending approval\s+waits")
        self.assertIn("before host-gate fallback or blocker classification", hierarchy)
        self.assertIn("Pending approval waits; it is not failed capacity or route exhaustion", hierarchy)
        self.assertIn("Pending approval waits; do not cancel the request, repeat it, count waiting as route exhaustion, or report a terminal blocker", recovery)
        self.assertIn("Once access is approved, retry the exact action", recovery)
        self.assertIn("Reconcile interrupted turns and uncertain writes before retrying", recovery)
        self.assertNotIn("Never ask the user to approve an internal helper", recovery)

    def test_host_gate_fallback_preserves_the_delegated_producer(self) -> None:
        recovery = " ".join((ROOT / "references" / "runtime-recovery.md").read_text(encoding="utf-8").split())
        self.assertIn("Only after the supported request is unavailable or actually denied", recovery)
        self.assertIn("A pending request does not justify that exception", recovery)
        self.assertIn("only when its use does not bypass an actual denial", recovery)

        owner = Swarm()
        owner.start_atomic(
            Role.CTRL,
            Task(
                "owner",
                "producer-owner",
                "creator",
                1,
                {},
                goal_id="goal-owner",
                subagent_exception=SubagentException.HOST_GATE,
                subagent_exception_reason="supported access request unavailable; separately permitted bounded producer inspection",
                delegation_contract=DelegationContract(
                    "owner",
                    "Return the bounded internal-helper inspection.",
                    "producer-owner",
                    ("receipts/owner.txt",),
                    ArtifactIdentity("owner","v1","non-artifact"),
                    ("receipts/owner.txt",),
                    (ProofClass.SOURCE,),
                    60,
                ),
            ),
        )
        self.assertEqual(owner.tasks["owner"].owner, "producer-owner")
        self.assertEqual(owner.tasks["owner"].topology_receipt, ("CTRL", "DOER", "atomic:isolated"))

    def test_actual_denial_and_other_error_causes_keep_their_boundaries(self) -> None:
        recovery = " ".join((ROOT / "references" / "runtime-recovery.md").read_text(encoding="utf-8").split())
        self.assertIn("An actual policy or automatic-review denial remains binding", recovery)
        self.assertIn("do not resubmit the denied action through another tool or runtime", recovery)
        self.assertIn("A disk-full, transport or credential error does not trigger access approval", recovery)
        self.assertIn("No blind privileged execution, ACL changes, credential reset, approval bypass or repeated permission loop is permitted", recovery)

    def test_loader_eval_requires_pending_access_wait_instead_of_fallback(self) -> None:
        payload = json.loads((ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))
        case = next(item for item in payload["evals"] if item["id"] == 62)
        fixture = json.loads((ROOT / case["files"][0]).read_text(encoding="utf-8"))
        self.assertTrue(fixture["operation"]["supported_access_approval_available"])
        self.assertEqual(fixture["access_approval"]["request_count"], 1)
        self.assertEqual(fixture["access_approval"]["decision"], "pending")
        self.assertFalse(fixture["fallback_receipt"]["attempted"])
        self.assertIn("Pending approval waits without cancellation, repeated requests, fallback dispatch or terminal blocker classification", case["assertions"])
        self.assertIn("An actual denial is respected", case["expected_output"])

    def test_genuine_user_authority_approval_still_blocks(self) -> None:
        skill = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in ("SKILL.md", "references/hierarchy.md"))
        hierarchy = (ROOT / "references" / "hierarchy.md").read_text(encoding="utf-8")
        recovery = (ROOT / "references" / "runtime-recovery.md").read_text(encoding="utf-8")
        hierarchy = " ".join(hierarchy.split())
        recovery = " ".join(recovery.split())

        self.assertRegex(skill, r"(?is)never grants external, provider,\s+destructive, or user-reserved authority")
        self.assertIn("user-reserved choices retain their normal approval gates", hierarchy)
        self.assertIn("does not waive approval for external or provider actions", recovery)


if __name__ == "__main__":
    unittest.main()
