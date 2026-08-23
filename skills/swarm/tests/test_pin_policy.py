import unittest
from pathlib import Path

from skills.swarm.runtime.core import PinDisposition, Role, close_pin_policy, pin_policy
from skills.swarm.scripts.swarm_config import DEFAULTS

ROOT=Path(__file__).resolve().parents[1]
PLUGIN_ROOT=ROOT.parents[1]/"plugins"/"swarm"/"skills"/"swarm"


class PinPolicyContractTests(unittest.TestCase):
    def test_compatibility_default_never_authorizes_ctrl_auto_pin(self):
        self.assertTrue(DEFAULTS["lifecycle"]["pin_created_tasks"])
        decision=pin_policy(Role.CTRL,top_level=True,pin_created_tasks=DEFAULTS["lifecycle"]["pin_created_tasks"])
        self.assertEqual(decision.disposition,PinDisposition.PLACEMENT_UNVERIFIED)
        self.assertFalse(decision.requests_pin)

    def test_asset_and_config_docs_disclose_host_owned_placement_boundary(self):
        for relative in ("assets/swarm-config.toml","references/config.md"):
            canonical=(ROOT/relative).read_text(encoding="utf-8")
            plugin=(PLUGIN_ROOT/relative).read_text(encoding="utf-8")
            self.assertEqual(canonical,plugin)
            self.assertIn("never authorizes automatic pinning",canonical)
            self.assertIn("explicit-user pin request",canonical)
            self.assertIn("host-owned placement receipt",canonical)
        asset=(ROOT/"assets"/"swarm-config.toml").read_text(encoding="utf-8")
        self.assertIn("pinned=false with placement_unverified",asset)

    def test_all_automatic_roles_are_unpinned(self):
        for role, top_level in [(Role.CTRL, True), (Role.LEAD, False), (Role.DOER, False), (Role.REVIEW, False), ("WATCHDOG", False), ("STORAGE", False), ("SIDECAR", False)]:
            with self.subTest(role=role):
                decision = pin_policy(role, top_level=top_level)
                self.assertFalse(decision.requests_pin)

    def test_top_level_ctrl_fails_closed_without_verified_placement(self):
        decision = pin_policy(Role.CTRL, top_level=True)
        self.assertEqual(decision.disposition, PinDisposition.PLACEMENT_UNVERIFIED)
        self.assertFalse(decision.requests_pin)
        self.assertIn("never pins", decision.reason)
        self.assertFalse(decision.remove_on_close)

    def test_review_handoff_without_explicit_host_user_receipt_is_unpinned(self):
        decision = pin_policy(Role.REVIEW, top_level=False, concrete_review_handoff=True)
        self.assertEqual(decision.disposition, PinDisposition.DEFAULT_UNPINNED)
        self.assertFalse(decision.requests_pin)

        for role in (Role.LEAD, Role.DOER, Role.REVIEW, "WATCHDOG", "STORAGE", "SIDECAR"):
            with self.subTest(role=role):
                nested = pin_policy(role, top_level=False)
                self.assertEqual(nested.disposition, PinDisposition.DEFAULT_UNPINNED)
                self.assertFalse(nested.requests_pin)

        self.assertEqual(
            pin_policy(Role.CTRL, top_level=False).disposition,
            PinDisposition.DEFAULT_UNPINNED,
        )
        self.assertEqual(
            pin_policy(Role.CTRL, top_level=True, pin_created_tasks=False).disposition,
            PinDisposition.DEFAULT_UNPINNED,
        )

    def test_explicit_user_flags_cannot_authorize_runtime_pin(self):
        for kwargs in (
            {"explicit_user_pin": True},
            {"concrete_review_handoff": True},
        ):
            with self.subTest(kwargs=kwargs):
                decision = pin_policy(Role.REVIEW, top_level=False, **kwargs)
                self.assertEqual(decision.disposition, PinDisposition.DEFAULT_UNPINNED)
                self.assertFalse(decision.requests_pin)

    def test_user_task_and_folder_custody_always_wins(self):
        custody_flags = (
            "user_pinned",
            "user_folder_pinned",
            "user_order_changed",
            "user_title_changed",
            "user_state_changed",
        )
        for flag in custody_flags:
            with self.subTest(flag=flag):
                decision = pin_policy(Role.CTRL, top_level=True, **{flag: True})
                self.assertEqual(decision.disposition, PinDisposition.PRESERVE_USER_STATE)
                self.assertFalse(decision.requests_pin)
                closed = close_pin_policy(decision, custody_verified=True, **{flag: True})
                self.assertEqual(closed.disposition, PinDisposition.PRESERVE_USER_STATE)


if __name__ == "__main__":
    unittest.main()
