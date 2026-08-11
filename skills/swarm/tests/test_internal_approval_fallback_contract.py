from __future__ import annotations

import unittest
from pathlib import Path

from skills.swarm.runtime.core import Role, SubagentException, Swarm, Task


ROOT = Path(__file__).resolve().parents[1]


class InternalApprovalFallbackContractTests(unittest.TestCase):
    def test_internal_helper_approval_falls_back_without_waiting_on_user(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        hierarchy = (ROOT / "references" / "hierarchy.md").read_text(encoding="utf-8")
        recovery = (ROOT / "references" / "runtime-recovery.md").read_text(encoding="utf-8")
        hierarchy = " ".join(hierarchy.split())
        recovery = " ".join(recovery.split())

        self.assertIn("abandon or cancel that attempt immediately", skill)
        self.assertIn("record unavailable subagent capacity", skill)
        self.assertIn("recorded as a host-gate exception", skill)
        self.assertIn("Never ask the user to approve an internal helper or read-only internal tool", skill)
        self.assertIn("An internal approval gate is failed capacity, not a user decision", hierarchy)
        self.assertIn("record a typed host-gate exception", recovery)

        owner = Swarm()
        owner.start_atomic(
            Role.CTRL,
            Task(
                "owner",
                "direct-owner",
                "creator",
                1,
                {},
                subagent_exception=SubagentException.HOST_GATE,
                subagent_exception_reason="read-only helper required host approval",
            ),
        )
        self.assertEqual(owner.tasks["owner"].owner, "direct-owner")

    def test_genuine_user_authority_approval_still_blocks(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        hierarchy = (ROOT / "references" / "hierarchy.md").read_text(encoding="utf-8")
        recovery = (ROOT / "references" / "runtime-recovery.md").read_text(encoding="utf-8")
        hierarchy = " ".join(hierarchy.split())
        recovery = " ".join(recovery.split())

        self.assertIn("external or provider actions, destructive actions", skill)
        self.assertIn("remain blocked until their normal designated authority approves them", skill)
        self.assertIn("user-reserved choices retain their normal approval gates", hierarchy)
        self.assertIn("does not waive approval for external or provider actions", recovery)


if __name__ == "__main__":
    unittest.main()
