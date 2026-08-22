import unittest

from skills.swarm.runtime.core import PinDisposition, Role, close_pin_policy, pin_policy
from skills.swarm.scripts.swarm_config import DEFAULTS


class PinPolicyContractTests(unittest.TestCase):
    def test_config_default_enables_ctrl_auto_pin_policy(self):
        self.assertTrue(DEFAULTS["lifecycle"]["pin_created_tasks"])

    def test_only_top_level_ctrl_auto_pins_with_verified_placement(self):
        decision = pin_policy(Role.CTRL, top_level=True, placement_verified=True)
        self.assertEqual(decision.disposition, PinDisposition.AUTO_PIN)

    def test_top_level_ctrl_fails_closed_without_verified_placement(self):
        decision = pin_policy(Role.CTRL, top_level=True)
        self.assertEqual(decision.disposition, PinDisposition.PLACEMENT_UNVERIFIED)
        self.assertFalse(decision.requests_pin)
        self.assertIn("pin not requested", decision.reason)
        self.assertFalse(decision.remove_on_close)

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

    def test_explicit_user_request_can_pin_non_ctrl(self):
        decision = pin_policy(Role.LEAD, top_level=False, explicit_user_pin=True)
        self.assertEqual(decision.disposition, PinDisposition.EXPLICIT_PIN)
        self.assertTrue(decision.requests_pin)
        self.assertFalse(decision.remove_on_close)

    def test_concrete_review_handoff_is_temporary_and_closes_safely(self):
        decision = pin_policy(Role.REVIEW, top_level=False, concrete_review_handoff=True)
        self.assertEqual(decision.disposition, PinDisposition.TEMPORARY_REVIEW_PIN)
        self.assertTrue(decision.requests_pin)
        self.assertTrue(decision.remove_on_close)
        self.assertEqual(
            close_pin_policy(decision, custody_verified=True).disposition,
            PinDisposition.DEFAULT_UNPINNED,
        )
        self.assertEqual(
            close_pin_policy(decision, custody_verified=False).disposition,
            PinDisposition.PRESERVE_USER_STATE,
        )
        self.assertEqual(
            close_pin_policy(decision, custody_verified=True, user_kept=True).disposition,
            PinDisposition.PRESERVE_USER_STATE,
        )

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
