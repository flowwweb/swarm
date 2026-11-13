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

    def test_archived_readback_cannot_hide_outstanding_duty(self):
        state = self.host(ack=True, title="🌱 Project 2", archived=True,
                          pinned=["p1-ctrl", "p2-new", "user-pin"])
        result = rotation_next_step(self.read(state, predecessor_in_flight=True))
        self.assertEqual((result.status, result.step), ("BLOCKED", "ARCHIVE"))

    def test_unverified_archived_readback_is_not_retirement_completion(self):
        state = self.host(ack=True, title="🌱 Project 2", archived=True,
                          pinned=["p1-ctrl", "p2-new", "user-pin"])
        result = rotation_next_step(self.read(state))
        self.assertEqual((result.status, result.step), ("UNVERIFIED", "ARCHIVE"))

    def test_rotation_cli_retains_one_pending_successor_across_restart(self):
        import json, os, sqlite3, subprocess, sys, tempfile
        from contextlib import closing
        from skills.swarm.runtime.core import Swarm, Task, Worker
        from skills.swarm.runtime.progress_events import ProgressLedger

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_path = root / "console.sqlite3"
            with closing(sqlite3.connect(state_path)) as db:
                db.execute("CREATE TABLE execution_dispatch_state (snapshot_json TEXT NOT NULL)")
                db.commit()
            envelope = dict(predecessor_id="p2-old", successor_id="p2-new", authorized=True,
                            baseline_pinned=list(self.BASE), pinned=["p1-ctrl", "p2-new", "user-pin"],
                            successor_ack=True, expected_title="Project 2", successor_title="Project 2",
                            predecessor_archived=True, predecessor_in_flight=False, user_keep_pinned=False,
                            capabilities=["title", "pin", "reorder", "unpin", "archive"],
                            retirement={"project_id": "project-2", "root_digest": "d" * 64, "goal_id": "goal-2", "handoff_digest": "a" * 64,
                                "automation_id": "automation-2", "collector_id": "p2-new", "ack_digest": None,
                                "release_receipt_id": None, "automation_target_id": None, "archive_receipt_id": None,
                                "active_controller_ids": None, "readback_id": None, "observed_at_ms": 1,
                                "unresolved_operations": []})

            def call(value):
                return subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "swarm_contract.py"), "rotate",
                                       "--console-state", str(state_path), "--rotation-ledger-root", str(root)],
                                      input=json.dumps(value), capture_output=True, text=True,
                                      env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})

            first = call(envelope)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            result = json.loads(first.stdout)
            self.assertEqual((result["status"], result["retirement"]["state"]), ("UNVERIFIED", "PENDING"))
            self.assertFalse(result["retirement"]["claims_verified"])
            records = ProgressLedger(root).project_task_handoffs()["records"]
            self.assertEqual((len(records), records[0]["new_owner"], records[0]["collector_id"]), (1, "p2-new", "p2-new"))
            task = Task("p2-old", "p2-old", "creator", 1, {}, goal_id="goal-2")
            old = Worker("p2-old", "lead", 1)
            old.task_ids.add(task.id)
            swarm = Swarm(workers={"p2-old": old, "p2-new": Worker("p2-new", "lead", 2)},
                          tasks={task.id: task}, request_lifecycle_ledger=ProgressLedger(root))
            swarm.reconcile_task_handoffs()
            self.assertFalse(task.handoff_active, "unverified CTRL rotation is not a generic task custody handoff")

            forged = call({**envelope, "retirement": {**envelope["retirement"], "claims_verified": True}})
            self.assertNotEqual(forged.returncode, 0, forged.stdout)
            self.assertEqual(ProgressLedger(root).project_task_handoffs()["records"], records)

            alternate = call({**envelope, "successor_id": "p2-other"})
            self.assertNotEqual(alternate.returncode, 0, alternate.stdout)
            self.assertEqual(ProgressLedger(root).project_task_handoffs()["records"], records)

            for field, value in (("handoff_digest", "b" * 64), ("automation_id", "automation-other"),
                                 ("collector_id", "collector-other"), ("root_digest", "e" * 64)):
                with self.subTest(immutable=field):
                    changed = call({**envelope, "retirement": {**envelope["retirement"], field: value}})
                    self.assertNotEqual(changed.returncode, 0, changed.stdout)
                    self.assertEqual(ProgressLedger(root).project_task_handoffs()["records"], records)

            wrong_ack = {**envelope["retirement"], "ack_digest": "b" * 64, "observed_at_ms": 2}
            wrong = call({**envelope, "retirement": wrong_ack})
            self.assertEqual((json.loads(wrong.stdout)["status"], json.loads(wrong.stdout)["step"]), ("BLOCKED", "ACK"))
            wrong_automation = {**wrong_ack, "ack_digest": "a" * 64, "release_receipt_id": "release-2",
                                "automation_target_id": "another-controller", "observed_at_ms": 3}
            wrong = call({**envelope, "retirement": wrong_automation})
            self.assertEqual((json.loads(wrong.stdout)["status"], json.loads(wrong.stdout)["step"]), ("BLOCKED", "AUTOMATION"))
            wrong_roster = {**wrong_automation, "automation_target_id": "p2-new",
                            "active_controller_ids": ["p2-old", "p2-new"], "observed_at_ms": 4}
            wrong = call({**envelope, "retirement": wrong_roster})
            self.assertEqual((json.loads(wrong.stdout)["status"], json.loads(wrong.stdout)["step"]), ("BLOCKED", "CONTROLLER"))

            apparent = {**wrong_roster, "active_controller_ids": ["p2-new"], "archive_receipt_id": "archive-2",
                        "readback_id": "readback-2", "observed_at_ms": 5}
            all_claimed = call({**envelope, "retirement": apparent})
            self.assertEqual((json.loads(all_claimed.stdout)["status"], json.loads(all_claimed.stdout)["retirement"]["state"]),
                             ("UNVERIFIED", "PENDING"), "complete-looking caller claims are not verified host evidence")

            claims = {**apparent, "observed_at_ms": 6,
                      "unresolved_operations": ["late-create-2"]}
            resumed = call({**envelope, "retirement": claims})
            self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            output = json.loads(resumed.stdout)
            self.assertEqual((output["status"], output["retirement"]["state"]), ("UNVERIFIED", "PENDING"))
            self.assertFalse(output["retirement"]["claims_verified"])
            records = ProgressLedger(root).project_task_handoffs()["records"]
            self.assertEqual(records[0]["rotation_observation"]["unresolved_operations"], ["late-create-2"])
            self.assertEqual(records[0]["rotation_observation"]["release_receipt_id"], "release-2")
            cursor = records[0]["event_seq"]
            self.assertEqual(call({**envelope, "retirement": claims}).returncode, 0)
            self.assertEqual(ProgressLedger(root).project_task_handoffs()["records"][0]["event_seq"], cursor)
            stale = call({**envelope, "retirement": {**claims, "observed_at_ms": 5}})
            self.assertNotEqual(stale.returncode, 0, stale.stdout)
            forgotten = call({**envelope, "retirement": {**claims, "observed_at_ms": 7, "unresolved_operations": []}})
            self.assertNotEqual(forgotten.returncode, 0, forgotten.stdout)
            rebound = call({**envelope, "retirement": {**claims, "observed_at_ms": 7, "archive_receipt_id": "archive-other"}})
            self.assertNotEqual(rebound.returncode, 0, rebound.stdout)
            preserved = {**envelope, "pinned": ["p1-ctrl", "p2-new", "p2-old", "user-pin"],
                         "predecessor_archived": False, "user_keep_pinned": True,
                         "retirement": {**claims, "observed_at_ms": 7}}
            kept = call(preserved)
            self.assertEqual((json.loads(kept.stdout)["status"], json.loads(kept.stdout)["step"]), ("PRESERVED", "UNPIN"))
            cleared = call({**preserved, "user_keep_pinned": False,
                            "retirement": {**preserved["retirement"], "observed_at_ms": 8}})
            self.assertNotEqual(cleared.returncode, 0, cleared.stdout)

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
        self.assertEqual(steps, ["ACK", "TITLE", "PIN", "UNPIN", "ARCHIVE", "UNVERIFIED"])
        self.assertEqual(state["pinned"], ["p1-ctrl", "p2-new", "user-pin"])
        self.assertTrue(state["archived"])
        self.assertEqual(rotation_next_step(self.read(state)).status, "UNVERIFIED", "caller readback is not host verification")

    def test_partial_transition_resumes_without_repeating_completed_steps(self):
        state = self.host(ack=True, title="🌱 Project 2", pinned=["p1-ctrl", "p2-new", "p2-old", "user-pin"])
        steps, _ = self.drive(state)
        self.assertEqual(steps, ["UNPIN", "ARCHIVE", "UNVERIFIED"], "successor already in slot is not re-pinned")
        state = self.host(ack=True, title="🌱 Project 2", pinned=["p1-ctrl", "p2-new", "user-pin"])
        self.assertEqual(self.drive(state)[0], ["ARCHIVE", "UNVERIFIED"])
        # Host appended the successor at the end: the complete list is reordered, nothing else moves.
        state = self.host(ack=True, title="🌱 Project 2", pinned=["p1-ctrl", "p2-old", "user-pin", "p2-new"])
        step = rotation_next_step(self.read(state))
        self.assertEqual((step.step, step.reorder_to), ("PIN", ("p1-ctrl", "p2-new", "p2-old", "user-pin")))

    def test_keep_pinned_exception_lease_and_user_order_changes_stop_safely(self):
        state = self.host(ack=True, title="🌱 Project 2", pinned=["p1-ctrl", "p2-new", "p2-old", "user-pin"])
        kept = rotation_next_step(self.read(state, user_keep_pinned=True))
        self.assertEqual((kept.status, kept.step), ("PRESERVED", "UNPIN"))
        leased = rotation_next_step(self.read(state, predecessor_in_flight=True))
        self.assertEqual((leased.status, leased.step), ("BLOCKED", "UNPIN"))
        unpinned = self.host(ack=True, title="🌱 Project 2", pinned=["p1-ctrl", "p2-new", "user-pin"])
        self.assertEqual(rotation_next_step(self.read(unpinned, predecessor_in_flight=True)).status, "BLOCKED")
        moved = self.host(ack=True, title="🌱 Project 2", pinned=["user-pin", "p1-ctrl", "p2-old"])
        self.assertEqual(rotation_next_step(self.read(moved)).status, "BLOCKED", "user reorder is preserved, not fought")
        self.assertEqual(rotation_next_step(self.read(self.host(), authorized=False)).status, "BLOCKED")

    def test_agent_cli_requires_collection_journal_and_does_not_authorize_host(self):
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
        code, result = cli(state)
        self.assertEqual(code, 0)
        self.assertFalse(result["host_mutation_authorized_by_runtime"])
        self.assertEqual((result["status"], result["step"]), ("UNVERIFIED", "COLLECTION"))
        self.assertEqual(result["reorder_to"], [])
        self.assertEqual(state["pinned"], list(self.BASE))
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
