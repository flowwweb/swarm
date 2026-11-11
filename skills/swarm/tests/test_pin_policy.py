import unittest
from pathlib import Path

from skills.swarm.runtime.core import (PinDisposition, Role, RotationReadback, close_pin_policy, pin_policy,
                                       rotation_next_step)
from skills.swarm.scripts.swarm_config import DEFAULTS

ROOT=Path(__file__).resolve().parents[1]
PLUGIN_ROOT=ROOT.parents[1]/"plugins"/"swarm"/"skills"/"swarm"


class PinPolicyContractTests(unittest.TestCase):
    def test_default_does_not_request_host_pin(self):
        self.assertFalse(DEFAULTS["lifecycle"]["pin_created_tasks"])
        decision=pin_policy(Role.CTRL,top_level=True,pin_created_tasks=DEFAULTS["lifecycle"]["pin_created_tasks"])
        self.assertEqual(decision.disposition,PinDisposition.DEFAULT_UNPINNED)
        self.assertFalse(decision.requests_pin)

    def test_asset_and_config_docs_disclose_opt_in(self):
        for relative in ("assets/swarm-config.toml","references/config.md"):
            canonical=(ROOT/relative).read_text(encoding="utf-8")
            plugin=(PLUGIN_ROOT/relative).read_text(encoding="utf-8")
            self.assertEqual(canonical,plugin)
            self.assertIn("top-level CTRL",canonical)
            self.assertIn("predecessor",canonical)
        asset=(ROOT/"assets"/"swarm-config.toml").read_text(encoding="utf-8")
        self.assertIn("pin_created_tasks = false",asset)

    def test_all_automatic_roles_are_unpinned(self):
        for role, top_level in [(Role.CTRL, True), (Role.LEAD, False), (Role.DOER, False), (Role.REVIEW, False), ("WATCHDOG", False), ("STORAGE", False), ("SIDECAR", False)]:
            with self.subTest(role=role):
                decision = pin_policy(role, top_level=top_level)
                self.assertFalse(decision.requests_pin)

    def test_configured_top_level_ctrl_requests_host_pin(self):
        decision = pin_policy(Role.CTRL, top_level=True, pin_created_tasks=True)
        self.assertEqual(decision.disposition, PinDisposition.HOST_PIN_REQUIRED)
        self.assertTrue(decision.requests_pin)
        self.assertIn("top-level CTRL", decision.reason)
        self.assertIn("fresh placement readback", decision.reason)
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


class RotationTransitionTests(unittest.TestCase):
    """Quiet authorized rotation driven only by fresh readback; the fake host is the only mutator."""

    BASE = ("p1-ctrl", "p2-old", "user-pin")

    def host(self, **overrides):
        state = {"pinned": list(self.BASE), "title": "", "archived": False, "ack": False}
        state.update(overrides)
        return state

    def read(self, state, **overrides):
        values = dict(predecessor_id="p2-old", successor_id="p2-new", authorized=True, baseline_pinned=self.BASE,
                      pinned=tuple(state["pinned"]), successor_ack=state["ack"], expected_title="🌱 Project 2",
                      successor_title=state["title"], predecessor_archived=state["archived"], predecessor_in_flight=False)
        values.update(overrides)
        return RotationReadback(**values)

    def apply(self, state, step):
        if step.step == "ACK":
            state["ack"] = True
        elif step.step == "TITLE":
            state["title"] = "🌱 Project 2"
        elif step.step == "PIN":
            state["pinned"] = list(step.reorder_to)
        elif step.step == "UNPIN":
            state["pinned"].remove("p2-old")
        elif step.step == "ARCHIVE":
            state["archived"] = True

    def drive(self, state, **overrides):
        steps = []
        for _ in range(8):
            step = rotation_next_step(self.read(state, **overrides))
            steps.append(step.step if step.status == "NEXT" else step.status)
            if step.status != "NEXT":
                return steps, step
            self.apply(state, step)
        self.fail("rotation did not converge")

    def test_successor_takes_predecessor_slot_and_other_projects_keep_order(self):
        state = self.host()
        steps, final = self.drive(state)
        self.assertEqual(steps, ["ACK", "TITLE", "PIN", "UNPIN", "ARCHIVE", "COMPLETE"])
        self.assertEqual(state["pinned"], ["p1-ctrl", "p2-new", "user-pin"])
        self.assertTrue(state["archived"])
        self.assertEqual(rotation_next_step(self.read(state)).status, "COMPLETE", "replay after completion is a no-op")

    def test_partial_transition_resumes_without_repeating_completed_steps(self):
        state = self.host(ack=True, title="🌱 Project 2", pinned=["p1-ctrl", "p2-new", "p2-old", "user-pin"])
        steps, _ = self.drive(state)
        self.assertEqual(steps, ["UNPIN", "ARCHIVE", "COMPLETE"], "successor already in slot is not re-pinned")
        state = self.host(ack=True, title="🌱 Project 2", pinned=["p1-ctrl", "p2-new", "user-pin"])
        self.assertEqual(self.drive(state)[0], ["ARCHIVE", "COMPLETE"])
        # Host appended the successor at the end: the complete list is reordered, nothing else moves.
        state = self.host(ack=True, title="🌱 Project 2", pinned=["p1-ctrl", "p2-old", "user-pin", "p2-new"])
        step = rotation_next_step(self.read(state))
        self.assertEqual((step.step, step.reorder_to), ("PIN", ("p1-ctrl", "p2-new", "p2-old", "user-pin")))

    def test_keep_pinned_exception_lease_and_user_order_changes_stop_safely(self):
        state = self.host(ack=True, title="🌱 Project 2", pinned=["p1-ctrl", "p2-new", "p2-old", "user-pin"])
        kept = rotation_next_step(self.read(state, user_keep_pinned=True))
        self.assertEqual((kept.status, kept.step), ("COMPLETE", "UNPIN"))
        leased = rotation_next_step(self.read(state, predecessor_in_flight=True))
        self.assertEqual((leased.status, leased.step), ("BLOCKED", "UNPIN"))
        unpinned = self.host(ack=True, title="🌱 Project 2", pinned=["p1-ctrl", "p2-new", "user-pin"])
        self.assertEqual(rotation_next_step(self.read(unpinned, predecessor_in_flight=True)).status, "BLOCKED")
        moved = self.host(ack=True, title="🌱 Project 2", pinned=["user-pin", "p1-ctrl", "p2-old"])
        self.assertEqual(rotation_next_step(self.read(moved)).status, "BLOCKED", "user reorder is preserved, not fought")
        self.assertEqual(rotation_next_step(self.read(self.host(), authorized=False)).status, "BLOCKED")

    def test_agent_cli_drives_quiet_rotation_from_readback_and_resumes(self):
        import json, subprocess, sys
        script = ROOT / "scripts" / "swarm_contract.py"
        def cli(state, **overrides):
            envelope = dict(predecessor_id="p2-old", successor_id="p2-new", authorized=True,
                            baseline_pinned=list(self.BASE), pinned=list(state["pinned"]), successor_ack=state["ack"],
                            expected_title="Project 2", successor_title=state["title"],
                            predecessor_archived=state["archived"], predecessor_in_flight=False,
                            user_keep_pinned=False, capabilities=["title", "pin", "reorder", "unpin", "archive"])
            envelope.update(overrides)
            run = subprocess.run([sys.executable, str(script), "rotate"], input=json.dumps(envelope),
                                 capture_output=True, text=True)
            return run.returncode, json.loads(run.stdout)
        state = self.host(ack=True, title="Project 2")
        steps = []
        for _ in range(6):
            code, result = cli(state)
            self.assertEqual(code, 0)
            self.assertFalse(result["host_mutation_authorized_by_runtime"])
            if result["status"] != "NEXT":
                break
            steps.append(result["step"])
            state["pinned"] = result["reorder_to"] or state["pinned"]
            if result["step"] == "UNPIN":
                state["pinned"].remove("p2-old")
            if result["step"] == "ARCHIVE":
                state["archived"] = True
        self.assertEqual((steps, result["status"]), (["PIN", "UNPIN", "ARCHIVE"], "COMPLETE"))
        self.assertEqual(state["pinned"], ["p1-ctrl", "p2-new", "user-pin"])
        code, rejected = cli(state, authorized="yes")
        self.assertEqual(code, 2)
        self.assertIn("wrong type", rejected["error"])

    def test_missing_capability_or_readback_stays_unverified_and_names_the_step(self):
        state = self.host(ack=True)
        self.assertEqual(rotation_next_step(self.read(state, successor_title=None)).step, "TITLE")
        self.assertEqual(rotation_next_step(self.read(state, capabilities=frozenset({"pin", "reorder"}))).status, "UNVERIFIED")
        state = self.host(ack=True, title="🌱 Project 2")
        for overrides, step in ((dict(pinned=None), "PIN"),
                                (dict(capabilities=frozenset({"title", "pin"})), "PIN")):
            result = rotation_next_step(self.read(state, **overrides))
            self.assertEqual((result.status, result.step), ("UNVERIFIED", step))
        state = self.host(ack=True, title="🌱 Project 2", pinned=["p1-ctrl", "p2-new", "user-pin"])
        result = rotation_next_step(self.read(state, predecessor_archived=None))
        self.assertEqual((result.status, result.step), ("UNVERIFIED", "ARCHIVE"))


if __name__ == "__main__":
    unittest.main()
