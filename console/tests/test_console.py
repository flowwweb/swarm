from __future__ import annotations

import copy
import importlib.util
import hashlib
import io
import os
import json
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from contextlib import closing
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SERVER = Path(__file__).resolve().parents[1] / "server.py"
SPEC = importlib.util.spec_from_file_location("swarm_console_tested", SERVER)
assert SPEC and SPEC.loader
console = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(console)
from runtime.progress_events import (  # noqa: E402
    build_agent_manifest,
    build_task_manifest,
    identity_manifest_event,
    role_manifest_reference,
    task_creation_binding_event,
    validate_progress_material_event,
    write_progress_pulse,
)
from runtime import (  # noqa: E402
    ArtifactIdentity,
    CodexAppServerAdapter,
    ContinuationSnapshot,
    ExecutionConfigGeneration,
    ExecutionDispatchState,
    ExecutionFailureKind,
    InvariantError,
)


class SwarmConsoleTests(unittest.TestCase):
    def test_account_limits_native_read_observation_and_usage_handler(self) -> None:
        from contextlib import contextmanager
        now = int(time.time() * 1000)
        wire = {"accountId": "private-account", "rateLimitsByLimitId": {
            "codex": {"primary": {"usedPercent": 60, "windowDurationMins": 300, "resetsAt": (now + 20_000_000) // 1000}, "secondary": None},
            "codex-spark": {"primary": {"usedPercent": 0, "windowDurationMins": 10080, "resetsAt": (now + 80_000_000) // 1000}}}}
        sent = []
        reply = {"id": 1, "result": wire}

        @contextmanager
        def session(cwd, *, timeout_seconds):
            self.assertEqual(cwd, self.codex_home)
            self.assertEqual(timeout_seconds, 10)
            def receive(predicate):
                self.assertFalse(predicate({"id": 2}))
                self.assertTrue(predicate(reply))
                return reply
            yield sent.append, receive

        bridge = console.CodexStdioBridge()
        with mock.patch.object(bridge, "command_session", session):
            sample = bridge.read_account_limits(self.codex_home)
        self.assertEqual(sent, [{"id": 1, "method": "account/rateLimits/read", "params": None}])
        self.assertEqual(sample["status"], "PARTIAL")
        self.assertNotIn("private-account", json.dumps(sample))
        self.assertEqual([row["remaining_percent"] for row in sample["windows"]], [40, None, 100, None])
        self.assertEqual(sample["windows"][0]["reset_at_ms"], wire["rateLimitsByLimitId"]["codex"]["primary"]["resetsAt"] * 1000)
        for bad in ({"id": 1, "error": {"code": -32601, "message": "private-account"}}, {"id": 1, "result": None}, {"id": 1, "result": {"rateLimitsByLimitId": []}}):
            reply = bad
            with mock.patch.object(bridge, "command_session", session):
                result = bridge.read_account_limits(self.codex_home)
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertEqual(result["windows"], [])
            self.assertNotIn("private-account", json.dumps(result))
        with mock.patch.object(bridge, "command_session", side_effect=OSError("private-account")):
            self.assertEqual(bridge.read_account_limits(self.codex_home)["reason"], "host_unavailable")

        app = console.App(self.codex_home, self.config, auto_bridge=bridge)
        diagnostic = {"sampled_at_ms": now, "cpu": {"available": True, "percent": 5}}
        overview = {"nodes": [], "links": [], "heartbeat_minutes": 30}
        with mock.patch.object(app, "_host_overview", return_value=overview), \
             mock.patch.object(app, "_ingest_progress_pulses_if_changed", return_value={}), \
             mock.patch.object(app, "_ingest_proof_events_if_changed"), \
             mock.patch.object(app, "evaluate_auto_once"), \
             mock.patch.object(app.diagnostics_collector, "collect", return_value=diagnostic), \
             mock.patch.object(bridge, "read_account_limits", return_value=sample) as read:
            app.observe_once()
        read.assert_called_once_with(self.codex_home)
        self.assertEqual(app.store.latest_diagnostics()["payload"]["cpu"], diagnostic["cpu"])
        restarted = console.App(self.codex_home, self.config, auto_bridge=bridge)
        handler = self._handler("127.0.0.1", "127.0.0.1:4788")
        handler.server.app = restarted
        handler.headers.replace_header("X-Swarm-Token", restarted.token)
        handler.path = "/api/usage-history?hours=1"
        handler._json = mock.Mock()
        with mock.patch.object(restarted, "_host_overview", return_value=overview), \
             mock.patch.object(bridge, "read_account_limits", side_effect=AssertionError("GET must not read host")):
            handler.do_GET()
        status, body = handler._json.call_args.args
        self.assertEqual(status, console.HTTPStatus.OK)
        quota = body["account_limits"]
        self.assertEqual(quota["scope"], "account")
        self.assertEqual(quota["windows"][0]["remaining_percent"], 40)
        self.assertEqual(quota["windows"][0]["forecast"]["status"], "UNKNOWN")
        self.assertEqual(body["task_usage"], [])
        handler.path = f"/api/usage-history?hours=720&after_ms={now-1000}&before_ms={now}"
        with mock.patch.object(restarted, "_host_overview", return_value=overview), \
             mock.patch.object(bridge, "read_account_limits", side_effect=AssertionError("history read must stay local")):
            handler.do_GET()
        status, dated = handler._json.call_args.args
        self.assertEqual(status, console.HTTPStatus.OK)
        self.assertEqual(dated["window"]["before_ms"], now)
        self.assertEqual(dated["account_history"]["items"][0]["sampled_at_ms"], now)
        self.assertEqual(dated["account_history"]["items"][0]["windows"][0]["remaining_percent"], 40)
        self.assertNotIn("private-account", json.dumps(dated))
        handler.path = f"/api/usage-history?after_ms={now-2000}&before_ms={now-1000}"
        with mock.patch.object(restarted, "_host_overview", return_value=overview):
            handler.do_GET()
        self.assertEqual(handler._json.call_args.args[1]["account_history"]["items"], [])
        with mock.patch.object(app, "_host_overview", return_value=overview), \
             mock.patch.object(app, "_ingest_progress_pulses_if_changed", return_value={}), \
             mock.patch.object(app, "_ingest_proof_events_if_changed"), \
             mock.patch.object(app, "evaluate_auto_once"), \
             mock.patch.object(app.diagnostics_collector, "collect", return_value={"sampled_at_ms": now + 1, "cpu": diagnostic["cpu"]}), \
             mock.patch.object(bridge, "read_account_limits", side_effect=OSError("offline")):
            app.observe_once()
        last = app.store.latest_diagnostics()["payload"]
        self.assertEqual(last["cpu"], diagnostic["cpu"])
        self.assertEqual(last["account_limits"]["status"], "UNKNOWN")
        self.assertEqual(console._account_limits_projection(app.store.diagnostics_history(), now + 1)["windows"], [])

    def test_account_limits_forecast_identity_freshness_and_null_contract(self) -> None:
        now = 10_000_000
        def record(at, used, *, account="a", reset=50_000, duration=300):
            result = console._normalize_account_limits({"accountId": account, "rateLimits": {"limitId": "codex",
                "primary": {"usedPercent": used, "windowDurationMins": duration, "resetsAt": reset}}})
            return {"sampled_at_ms": at, "payload": {"account_limits": result}}
        def project(records, time_ms=now):
            return console._account_limits_projection(records, time_ms)["windows"][0]
        rows = [record(now - i * 60_000, 60 - i * 10 // 15) for i in range(16)]
        result = project(rows)
        self.assertEqual(result["forecast"]["rate_percentage_points_per_hour"], 40)
        self.assertEqual(result["forecast"]["exhaustion_at_ms"], now + 3_600_000)
        self.assertEqual(result["observed_interval_ms"], 900_000)
        self.assertEqual([result["history"][i]["remaining_percent"] for i in (0, -1)], [50, 40])
        self.assertEqual(len(result["history"]), 16)
        self.assertEqual(console._account_limits_projection(rows, now)["forecast_policy"]["maximum_gap_ms"], 120_000)
        self.assertEqual(project([rows[0], *rows[2:]])["forecast"]["status"], "ESTIMATED")
        for gapped in ([rows[0], *rows[3:]], [rows[0], record(now - 120_001, 59), *rows[3:]], [rows[0], rows[-1]]):
            stopped = project(gapped)
            self.assertEqual(stopped["forecast"]["status"], "UNKNOWN")
            self.assertEqual(len(stopped["history"]), 1)
        for previous in (record(now - 60_000, 50, account="b"), record(now - 60_000, 50, reset=60_000),
                         record(now - 60_000, 50, duration=10080), record(now - 60_000, 70)):
            self.assertEqual(project([rows[0], previous, *rows[2:]])["forecast"]["status"], "UNKNOWN")
        self.assertEqual(project([rows[0], record(now - 10_000, 50)])["forecast"]["status"], "UNKNOWN")
        self.assertEqual(project(rows, now + 300_001)["status"], "STALE")
        self.assertEqual(project(rows, now + 300_001)["forecast"]["status"], "UNKNOWN")
        expired = project([record(now, 60, reset=10_000)])
        self.assertEqual(expired["status"], "STALE")
        self.assertEqual(expired["forecast"]["status"], "UNKNOWN")
        expired_record = record(now, 60, reset=10_000)
        expired_record["payload"]["account_limits"]["windows"] = expired_record["payload"]["account_limits"]["windows"][:1]
        self.assertEqual(console._account_limits_projection([expired_record], now)["status"], "STALE")
        current_record = record(now, 60)
        current_record["payload"]["account_limits"]["windows"] = current_record["payload"]["account_limits"]["windows"][:1]
        self.assertEqual(console._account_limits_projection([current_record], now)["status"], "KNOWN")
        expired_record["payload"]["account_limits"]["windows"][0]["window"] = "secondary"
        current_record["payload"]["account_limits"]["windows"].extend(expired_record["payload"]["account_limits"]["windows"])
        self.assertEqual(console._account_limits_projection([current_record], now)["status"], "PARTIAL")
        self.assertEqual(project([record(now - i * 60_000, 60) for i in range(16)])["forecast"]["status"], "NO_MEASURABLE_BURN")
        self.assertEqual(project([record(now, 100)])["forecast"]["status"], "EXHAUSTED")
        reset_first = project([record(now - i * 60_000, 60 - i * 10 // 15, reset=11_000) for i in range(16)])
        self.assertEqual(reset_first["forecast"]["status"], "RESET_BEFORE_EXHAUSTION")
        self.assertIsNone(reset_first["forecast"]["exhaustion_at_ms"])
        anonymous = project([record(now, 60, account=None), record(now - 900_000, 50, account=None)])
        self.assertEqual(len(anonymous["history"]), 1)
        self.assertEqual(anonymous["forecast"]["status"], "UNKNOWN")
        for used in (None, True, "0", -1, 101):
            self.assertIsNone(project([record(now, used)])["remaining_percent"])
        self.assertEqual(console._account_limits_projection([], now)["status"], "UNKNOWN")

    def test_docker_status_suppresses_windows_console(self) -> None:
        with mock.patch.object(console.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), mock.patch.object(
            console.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="swarm-console\n"),
        ) as run:
            result = console.DiagnosticsCollector._docker_status()
        self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000000)
        self.assertEqual(run.call_args.args[0], ["docker", "ps", "--filter", "name=swarm-console", "--format", "{{.Names}}"])
        self.assertTrue(result["available"])
        self.assertEqual(result["container_count"], 1)

    def test_command_session_deadline_preserves_exact_turn_custody(self) -> None:
        self._assert_command_session_custody({"result": {"turn": {"id": "owned-turn"}}})

    def test_command_session_correlated_rejection_cleans_idle_process(self) -> None:
        self._assert_command_session_custody({"error": {"code": -32602, "message": "invalid input"}}, rejected=True)

    def test_command_session_unknown_ack_retains_process(self) -> None:
        self._assert_command_session_custody(None)

    def test_command_session_contradictory_error_retains_process(self) -> None:
        self._assert_command_session_custody({"error": {"code": -32602, "message": "invalid input"},
            "result": {"turn": {"id": "owned-turn"}}})

    def test_command_session_stderr_terminal_cannot_release_custody(self) -> None:
        self._assert_command_session_custody({"result": {"turn": {"id": "owned-turn"}}}, diagnostic_terminal=True)

    def test_command_session_post_return_approval_is_scoped_once_only(self) -> None:
        self._assert_command_session_custody({"result": {"turn": {"id": "owned-turn"}}}, approvals=True)

    def _assert_command_session_custody(self, turn_response, *, rejected=False, diagnostic_terminal=False, approvals=False) -> None:
        import queue
        events = queue.Queue()
        processed = threading.Event()
        reader_done = threading.Event()
        terminated = threading.Event()
        written = []
        clock = [0.0]
        diagnostics = queue.Queue()
        diagnostic_done = threading.Event()

        class Diagnostics:
            def readline(self, limit):
                assert limit == 8192
                value = diagnostics.get()
                if value is None:
                    diagnostic_done.set()
                    return ""
                return json.dumps(value) + "\n"

        class Output:
            def __iter__(self):
                try:
                    while True:
                        item = events.get()
                        if item is None:
                            return
                        yield json.dumps(item) + "\n"
                        processed.set()
                finally:
                    reader_done.set()

        class Input:
            def write(self, value):
                message = json.loads(value)
                written.append(message)
                results = {"initialize": {}, "thread/start": {"thread": {"id": "owned-thread"}}}
                if "method" not in message:
                    return
                if message["method"] in results:
                    events.put({"id": message["id"], "result": results[message["method"]]})
                elif message["method"] == "turn/start" and turn_response is not None:
                    if approvals:
                        events.put({"id": message["id"], "method": "item/tool/requestUserInput", "params": {}})
                    events.put({"id": message["id"], **turn_response})

            def flush(self):
                pass

        class Process:
            stdin = Input()
            stdout = Output()
            terminate_count = 0
            kill_count = 0

            def poll(self):
                return 0 if terminated.is_set() else None

            def terminate(self):
                self.terminate_count += 1
                terminated.set()
                events.put(None)

            def kill(self):
                self.kill_count += 1

            def wait(self, timeout=None):
                if not terminated.wait(timeout):
                    raise console.subprocess.TimeoutExpired("fake", timeout)
                return 0

        process = Process()
        if diagnostic_terminal:
            process.stderr = Diagnostics()
        factory = mock.Mock(return_value=process)
        bridge = console.CodexStdioBridge(factory, executable_resolver=lambda: ("codex-test", "0.153.4"))
        terminal = {"method": "turn/completed", "params": {
            "threadId": "owned-thread", "turnId": "owned-turn", "status": "completed"}}

        def deliver(event):
            processed.clear()
            events.put(event)
            self.assertTrue(processed.wait(2), "existing reader must consume the event")

        try:
            with mock.patch.object(console.time, "monotonic", side_effect=lambda: clock[0]):
                with bridge.command_session(self.root, retain_turn=True, approval_project_id="project" if approvals else "") as (send, receive):
                    send({"id": 1, "method": "thread/start", "params": {"cwd": str(self.root)}})
                    receive(lambda item: item.get("id") == 1)
                    send({"id": 2, "method": "turn/start", "params": {"threadId": "owned-thread", "input": []}})
                    if turn_response is not None:
                        response = receive(lambda item: item.get("id") == 2)
                        self.assertNotIn("method", response, "inbound request ID must not satisfy an outbound RPC")
                        if rejected:
                            self.assertIn("error", response)
                    clock[0] = console.AUTO_BRIDGE_TIMEOUT_SECONDS + 1
                    if not rejected:
                        with self.assertRaises(TimeoutError):
                            receive(lambda item: item.get("method") == "turn/completed")
                if rejected:
                    self.assertTrue(terminated.wait(2))
                    self.assertTrue(reader_done.wait(2))
                    self.assertEqual((process.terminate_count, process.kill_count), (1, 0))
                    self.assertEqual(factory.call_count, 1)
                    self.assertEqual([item["method"] for item in written], ["initialize", "initialized", "thread/start", "turn/start"])
                    return
                self.assertEqual((process.terminate_count, process.kill_count), (0, 0))
                if approvals:
                    request = {"id": 2, "method": "item/commandExecution/requestApproval", "params": {
                        "threadId": "owned-thread", "turnId": "owned-turn", "itemId": "item-1",
                        "cwd": str(self.root), "command": "read-only-check", "availableDecisions": ["accept", "decline", "cancel"]}}
                    deliver(request)
                    rows = bridge.approval_requests("project", str(self.root))
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(bridge.approval_requests("other", str(self.root)), [])
                    row = rows[0]
                    self.assertEqual(row["permitted_decisions"], ["accept", "decline", "cancel"])
                    for changes in ({"kind": "writeStdin"}, {"kind": None}, {"environmentId": "unbound-remote"}, {"kind": "command", "environmentId": "unbound-local"}):
                        blocked = copy.deepcopy(request)
                        blocked["params"].update(changes)
                        # Same native ID: invalid variants must neither acquire nor replace authority.
                        deliver(blocked)
                        self.assertEqual(bridge.approval_requests("project", str(self.root)), rows)
                        forged = {key: row[key] for key in ("approval_id", "project_id", "thread_id", "turn_id", "request_digest")}
                        forged.update(request_digest=console._auto_digest(blocked), decision="accept", acknowledge=True)
                        with self.assertRaises(console.ConsoleError):
                            bridge.respond_approval(forged, str(self.root))
                        blocked["id"] = "withheld-" + console._auto_digest(changes)
                        deliver(blocked)
                        self.assertEqual(bridge.approval_requests("project", str(self.root)), rows)
                    payload = {key: row[key] for key in ("approval_id", "project_id", "thread_id", "turn_id", "request_digest")}
                    payload.update(decision="decline", acknowledge=True)
                    for field, value in (("acknowledge", False), ("project_id", "other"), ("turn_id", "stale"), ("request_digest", "wrong"), ("decision", "acceptForSession")):
                        with self.assertRaises(console.ConsoleError):
                            bridge.respond_approval({**payload, field: value}, str(self.root))
                    def post_approval(token):
                        handler = self._handler("127.0.0.1", "127.0.0.1:4788", token=token)
                        handler.server.app.auto_bridge = bridge
                        handler.server.app._canonical_project_root = mock.Mock(return_value=self.root)
                        handler.path = "/api/tasks/approvals/respond"
                        handler._payload = mock.Mock(return_value=payload)
                        handler._json = mock.Mock()
                        handler._error = mock.Mock()
                        handler.do_POST()
                        return handler
                    denied = post_approval("invalid")
                    denied._error.assert_called_once()
                    self.assertEqual(len(bridge.approval_requests("project", str(self.root))), 1)
                    allowed = post_approval("secret")
                    allowed._error.assert_not_called()
                    self.assertEqual(allowed._json.call_args.args[1]["status"], "SUBMITTED")
                    self.assertEqual(written[-1], {"id": 2, "result": {"decision": "decline"}})
                    with self.assertRaises(console.ConsoleError):
                        bridge.respond_approval(payload, str(self.root))
                    self.assertFalse(terminated.is_set())
                    for offered, expected in ((["cancel", "unknown", "decline"], ["decline", "cancel"]),
                                              (["unknown", "acceptForSession"], []), (None, ["accept", "decline", "cancel"]), ("accept", [])):
                        variant = copy.deepcopy(request)
                        variant["id"] = "offers-" + console._auto_digest(offered)
                        if offered is None:
                            variant["params"].pop("availableDecisions")
                        else:
                            variant["params"]["availableDecisions"] = offered
                        deliver(variant)
                        projected = bridge.approval_requests("project", str(self.root))[0]
                        self.assertEqual(projected["permitted_decisions"], expected)
                        projected["permitted_decisions"].append("not-authorized")
                        self.assertEqual(bridge.approval_requests("project", str(self.root))[0]["permitted_decisions"], expected)
                        decision_payload = {**payload, "approval_id": projected["approval_id"], "request_digest": projected["request_digest"]}
                        for decision in ("accept", "decline", "cancel"):
                            if decision not in expected:
                                with self.assertRaises(console.ConsoleError):
                                    bridge.respond_approval({**decision_payload, "decision": decision}, str(self.root))
                        if expected:
                            bridge.respond_approval({**decision_payload, "decision": expected[0]}, str(self.root))
                            self.assertEqual(written[-1], {"id": variant["id"], "result": {"decision": expected[0]}})
                        else:
                            deliver({"method": "serverRequest/resolved", "params": {"threadId": "owned-thread", "requestId": variant["id"]}})
                    request["id"] = "uncertain-write"
                    request["params"].update(kind="command", environmentId=None)
                    deliver(request)
                    uncertain = bridge.approval_requests("project", str(self.root))[0]
                    uncertain_payload = {**payload, "approval_id": uncertain["approval_id"], "request_digest": uncertain["request_digest"]}
                    with mock.patch.object(process.stdin, "flush", side_effect=OSError("uncertain delivery")):
                        with self.assertRaises(OSError):
                            bridge.respond_approval(uncertain_payload, str(self.root))
                    with self.assertRaises(console.ConsoleError):
                        bridge.respond_approval(uncertain_payload, str(self.root))
                    request["id"] = "resolved"
                    deliver(request)
                    deliver({"method": "serverRequest/resolved", "params": {"threadId": "owned-thread", "requestId": "resolved"}})
                    self.assertEqual(bridge.approval_requests("project", str(self.root)), [])
                    request["id"] = "pending-at-terminal"
                    deliver(request)
                    self.assertEqual(len(bridge.approval_requests("project", str(self.root))), 1)
                if diagnostic_terminal:
                    diagnostics.put(terminal)
                    diagnostics.put(None)
                    self.assertTrue(diagnostic_done.wait(2))
                    self.assertFalse(terminated.is_set(), "stderr terminal must not release process custody")
                deliver({"id": 99, "method": "item/commandExecution/requestApproval", "params": {
                    "threadId": "owned-thread", "turnId": "owned-turn"}})
                self.assertFalse(terminated.is_set(), "approval waiting is neither complete nor canceled")
                for changes in ({"turnId": "other-turn"}, {"threadId": "other-thread"}, {"status": "inProgress"},
                    {"turn": {"id": "conflicting-turn"}}):
                    unrelated = copy.deepcopy(terminal)
                    unrelated["params"].update(changes)
                    deliver(unrelated)
                    self.assertFalse(terminated.is_set())
                if turn_response is None:
                    deliver({"id": 2, "result": {"turn": {"id": "owned-turn"}}})
                deliver(terminal)
                self.assertTrue(terminated.wait(2))
                self.assertTrue(reader_done.wait(2))
                if approvals:
                    self.assertEqual(bridge.approval_requests("project", str(self.root)), [])
                self.assertEqual((process.terminate_count, process.kill_count), (1, 0))
                self.assertEqual(factory.call_count, 1)
                self.assertEqual([item["method"] for item in written if "method" in item], ["initialize", "initialized", "thread/start", "turn/start"])
        finally:
            if not terminated.is_set():
                events.put({"id": 2, "result": {"turn": {"id": "owned-turn"}}})
                events.put(terminal)
            self.assertTrue(terminated.wait(2), "test process custody must settle")
            self.assertTrue(reader_done.wait(2), "no unfinished reader session")

    def test_task_history_roster_caps_in_memory(self) -> None:
        class RetainedConnection(sqlite3.Connection):
            def close(self):
                pass  # Reuse this in-memory snapshot across the four reads.
        connection = sqlite3.connect(":memory:", factory=RetainedConnection)
        connection.row_factory = sqlite3.Row
        with closing(sqlite3.connect(self.database)) as source:
            source.backup(connection)
        connection.execute("DELETE FROM threads")
        connection.execute("UPDATE project_roots SET path=?", (str(self.root),))
        connection.commit()
        app = console.App(self.codex_home, self.config)
        try:
            with mock.patch.object(console, "_readonly_connection", return_value=connection), mock.patch.object(
                app, "_canonical_project_root", return_value=self.root
            ):
                def roster(count, cwd):
                    connection.rollback()
                    connection.execute("DELETE FROM threads")
                    connection.executemany("INSERT INTO threads(id,title,cwd,archived) VALUES(?,?,?,0)",
                        ((f"t{i:05}", "Retained", cwd) for i in range(count)))
                    connection.commit()
                    return app.task_history_roster({"project_id": "project:alpha"})
                exact = roster(500, str(self.root))
                self.assertEqual((exact["status"], len(exact["items"]), exact["truncated"]), ("AVAILABLE", 500, False))
                overflow = roster(501, str(self.root))
                self.assertEqual((overflow["status"], len(overflow["items"]), overflow["truncated"]), ("PARTIAL", 500, True))
                self.assertEqual(overflow["items"], exact["items"])
                exact_scan = roster(10000, "C:/foreign")
                self.assertEqual((exact_scan["status"], exact_scan["items"], exact_scan["truncated"]), ("EMPTY", [], False))
                scan_overflow = roster(10001, "C:/foreign")
                self.assertEqual((scan_overflow["status"], scan_overflow["items"], scan_overflow["truncated"]), ("PARTIAL", [], True))
        finally:
            sqlite3.Connection.close(connection)

    def test_task_history_authenticated_observed_independent_bounded_read(self) -> None:
        from contextlib import contextmanager
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE project_roots SET path=?", (str(self.root),))
            connection.execute("UPDATE threads SET cwd=?, title='Ordinary task' WHERE id='task'", (str(self.root),))
            connection.execute("DELETE FROM thread_spawn_edges")
            connection.commit()
        app = console.App(self.codex_home, self.config)
        observed = next(node for node in app._host_overview(refresh=True)["nodes"] if node["id"] == "task")
        self.assertEqual(observed["project_binding_state"], "ROOT")
        self.assertFalse(observed.get("agent_role"))
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE threads SET updated_at=1,updated_at_ms=1000 WHERE id='task'")
            connection.commit()
        self.assertFalse(any(node["id"] == "task" for node in app._host_overview(refresh=True)["nodes"]))
        roster = app.task_history_roster({"project_id": "project:alpha"})
        self.assertEqual(roster["status"], "AVAILABLE")
        self.assertFalse(roster["truncated"])
        self.assertEqual(roster["items"], [{"thread_id": "task", "project_id": "project:alpha", "title": "Ordinary task"}])
        self.assertEqual(app.task_history_roster({"project_id": "missing"})["status"], "UNAVAILABLE")
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE threads SET archived=1 WHERE id='task'")
            connection.commit()
        self.assertEqual(app.task_history_roster({"project_id": "project:alpha"})["status"], "EMPTY")
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE threads SET archived=0 WHERE id='task'")
            connection.commit()
        messages = [{"type": "userMessage", "id": "u", "content": [{"type": "text", "text": "Hello"}, {"type": "image", "url": "secret"}]},
                    {"type": "reasoning", "id": "r", "text": "private reasoning"},
                    {"type": "commandExecution", "id": "c", "aggregatedOutput": "private terminal"},
                    {"type": "agentMessage", "id": "a", "text": "Done\napi_key=hidden\nC:/private/file"}]
        response = {"id": 1, "result": {"thread": {"id": "task", "cwd": str(self.root), "turns": [{"id": "turn", "items": messages}]}}}
        calls = []
        @contextmanager
        def session(cwd):
            self.assertEqual(cwd, self.root.resolve())
            def send(message):
                self.assertEqual(message, {"id": 1, "method": "thread/read", "params": {"threadId": "task", "includeTurns": True}})
                calls.append(message)
            yield send, lambda predicate: response
        app.auto_bridge.command_session = session
        def post(thread_id="task", token=None, roster=False):
            handler = self._handler("127.0.0.1", "127.0.0.1:4788", token=app.token if token is None else token)
            handler.server.app = app
            handler.path = "/api/tasks/history-roster" if roster else "/api/tasks/history"
            handler._payload = mock.Mock(return_value={"project_id": "project:alpha"} if roster else {"project_id": "project:alpha", "thread_id": thread_id})
            handler._json, handler._error = mock.Mock(), mock.Mock()
            handler.do_POST()
            return handler
        post(token="wrong")._error.assert_called_once()
        post(token="wrong", roster=True)._error.assert_called_once()
        self.assertEqual(post(roster=True)._json.call_args.args[1]["items"], roster["items"])
        post("unsafe")._error.assert_called_once()
        self.assertEqual(calls, [])
        read = post()._json.call_args.args[1]
        self.assertEqual(read["status"], "AVAILABLE")
        self.assertEqual([(item["id"], item["role"]) for item in read["items"]], [("u", "user"), ("a", "assistant")])
        self.assertEqual(read["items"][1]["text"], "Done\n[redacted]\n[path]")
        self.assertNotIn("reasoning", json.dumps(read))
        self.assertEqual(post()._json.call_args.args[1]["cursor"], read["cursor"])
        response["result"]["thread"]["turns"] = []
        self.assertEqual(post()._json.call_args.args[1]["status"], "EMPTY")
        response["error"] = {"code": -32601, "message": "unsupported"}
        self.assertEqual(post()._json.call_args.args[1]["status"], "UNAVAILABLE")
        del response["error"]
        response["result"]["thread"]["cwd"] = str(self.codex_home)
        self.assertEqual(post()._json.call_args.args[1]["status"], "UNAVAILABLE")
        response["result"]["thread"]["cwd"] = str(self.root)
        response["result"]["thread"]["turns"] = [{"id": "turn", "items": [{"type": "agentMessage", "id": f"m{i}", "text": "🙂" * 4200} for i in range(110)]}]
        self.assertEqual(post()._json.call_args.args[1]["reason"], "HISTORY_BOUND_EXCEEDED")
        response["result"]["thread"]["turns"][0]["items"] = [{"type": "agentMessage", "id": f"m{i}", "text": "🙂" * 100} for i in range(110)]
        bounded = post()._json.call_args.args[1]
        self.assertTrue(bounded["truncated"])
        self.assertLessEqual(len(bounded["items"]), 100)
        self.assertLessEqual(len(json.dumps(bounded["items"]).encode()), 65536)
        self.assertEqual(bounded["items"][-1]["id"], "m109")
        response["result"]["thread"]["turns"][0]["items"] = [messages[0], messages[0]]
        self.assertEqual(post()._json.call_args.args[1]["status"], "UNAVAILABLE")
        self.assertEqual(app.progress_ledger.replay()["connector_receipts"], {})

    def test_create_bound_task_calls_connector_and_replays_retained_binding(self) -> None:
        from contextlib import contextmanager
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE project_roots SET path=? WHERE project_id=?", (str(self.root), "project:alpha"))
            connection.commit()
        app = console.App(self.codex_home, self.config)
        root = app._canonical_project_root("project:alpha")
        role = next(item for item in app.builtin_role_manifests if item["id"] == "developer")
        task = build_task_manifest(manifest_id="task:test", task_id="draft-only", task_name="Bound task",
            project_id="project:alpha", ctrl_id="ctrl-a",
            milestones=[{"milestone_id": "m", "order": 0, "title": "M", "verification_policy": "source", "supersedes_milestone_id": None}],
            blocks=[{"block_id": "b", "milestone_id": "m", "order": 0, "title": "B", "verification_policy": "source", "estimate_minutes": 1, "weight": None, "supersedes_block_id": None}])
        contract = {
            "role_manifest": role,
            "task_manifest_draft": {key: value for key, value in task.items() if key not in {"task_id", "manifest_digest"}},
            "parent_task_id": None, "topology_manifest_receipt_id": "topology-receipt",
            "task_receipt_id": "task-receipt", "milestone_receipts": [{"id": "m", "receipt_id": "m-receipt"}],
            "block_receipts": [{"id": "b", "receipt_id": "b-receipt"}],
            "explicit_empty_work_receipt_id": None, "independent_host_task": False,
        }
        now = int(time.time() * 1000)
        instruction = "Create the explicitly authorized task."
        payload = {"acknowledge": True, "instruction": instruction, "envelope": {
            "command_id": "create-one", "idempotency_key": "create-one-key", "action": "MANUAL_AGENT",
            "project_id": "project:alpha", "root_digest": console._auto_digest({"project_id": "project:alpha", "canonical_root": console._normalized_project_path(str(root))}),
            "ctrl_id": "ctrl-a", "target_intent": "NEW_THREAD", "target_thread_id": "",
            "payload_digest": hashlib.sha256(instruction.encode()).hexdigest(), "expected_ledger_revision": 0,
            "submitted_at_ms": now, "expires_at_ms": now + 60000, "task_creation": contract}}
        sent = []
        responses = [{"thread": {"id": "host-new", "cwd": str(root)}}, {"turn": {"id": "turn-new"}}]
        @contextmanager
        def session(cwd, *, retain_turn=False, approval_project_id=""):
            self.assertEqual(approval_project_id, "project:alpha")
            self.assertEqual(cwd, root)
            self.assertTrue(retain_turn)
            def send(message):
                sent.append(message)
                if message["method"] == "thread/start":
                    self.assertEqual(message["params"], {"cwd": str(root)})
                elif message["method"] == "turn/start":
                    self.assertEqual(message["params"], {"threadId": "host-new", "cwd": str(root),
                        "input": [{"type": "text", "text": instruction, "text_elements": []}]})
                else:
                    self.assertEqual(message["method"], "thread/read")
            def receive(predicate):
                terminal = {"method": "turn/completed", "params": {"threadId": "host-new", "turnId": "turn-new", "status": "completed"}}
                if predicate(terminal):
                    return terminal
                return {"id": sent[-1]["id"], "result": responses.pop(0)}
            yield send, receive
        app.auto_bridge.command_session = session

        def post(body, *, token=None):
            handler = self._handler("127.0.0.1", "127.0.0.1:4788", token=app.token if token is None else token)
            handler.server.app = app
            handler.path = "/api/tasks/create"
            handler._payload = mock.Mock(return_value=body)
            handler._json = mock.Mock()
            handler._error = mock.Mock()
            handler.do_POST()
            return handler

        denied = post(payload, token="wrong")
        denied._error.assert_called_once()
        self.assertEqual(sent, [])
        wrong = copy.deepcopy(payload)
        wrong["envelope"]["root_digest"] = "a" * 64
        post(wrong)._error.assert_called_once()
        self.assertEqual(sent, [])
        for changed in ("acknowledge", "payload_digest", "expires_at_ms"):
            rejected = copy.deepcopy(payload)
            if changed == "acknowledge":
                rejected[changed] = False
            elif changed == "payload_digest":
                rejected["envelope"][changed] = "b" * 64
            else:
                rejected["envelope"].update(submitted_at_ms=now - 120000, expires_at_ms=now - 60000)
            post(rejected)._error.assert_called_once()
            self.assertEqual(sent, [])
        self.assertEqual(app.progress_ledger.replay()["connector_receipts"], {})
        result = post(payload)
        result._error.assert_not_called()
        receipt = result._json.call_args.args[1]
        self.assertFalse(app.write_lock.locked(), "HTTP submission must release shared write custody after dispatch")
        self.assertEqual((receipt["status"], receipt["thread_id"], receipt["turn_id"]), ("RESULT", "host-new", "turn-new"))
        self.assertFalse(receipt["work_completed"])
        self.assertEqual(receipt["host_turn_status"], "UNKNOWN")
        binding = app.progress_ledger.project_task_creation_bindings("project:alpha")
        self.assertIn("host-new", json.dumps(binding))
        self.assertIn("b-receipt", json.dumps(binding))
        before = app.progress_ledger._state.path.read_bytes()
        self.assertNotIn(instruction.encode(), before)
        app = console.App(self.codex_home, self.config)
        app.auto_bridge.command_session = session
        replay = post(payload)._json.call_args.args[1]
        self.assertEqual(replay["status"], "REPLAY")
        self.assertEqual(app.progress_ledger._state.path.read_bytes(), before)
        self.assertEqual(len(sent), 2)

        uncertain = copy.deepcopy(payload)
        uncertain["envelope"].update(command_id="uncertain", idempotency_key="uncertain-key",
            expected_ledger_revision=app.progress_ledger.replay()["cursor"]["event_seq"])
        responses.extend([{"thread": {"id": "host-new", "cwd": str(root)}}, {}])
        pending = post(uncertain)._json.call_args.args[1]
        self.assertEqual(pending["status"], "PENDING")
        self.assertFalse(pending["work_completed"])
        facts = app.progress_ledger.replay()["connector_receipts"]["uncertain-key"]["receipts"]
        self.assertEqual([fact["status"] for fact in facts], ["COMMAND", "ACKNOWLEDGED"])
        app = console.App(self.codex_home, self.config)
        app.auto_bridge.command_session = session
        responses.append({"thread": {"id": "host-new", "cwd": str(root), "turns": []}})
        self.assertEqual(post(uncertain)._json.call_args.args[1]["status"], "PENDING")
        self.assertEqual([item["method"] for item in sent], ["thread/start", "turn/start", "thread/start", "turn/start", "thread/read"])
        self.assertEqual(app.progress_ledger.project_task_creation_bindings("project:alpha")["bindings"], binding["bindings"])
        wrong_host = copy.deepcopy(payload)
        wrong_host["envelope"].update(command_id="wrong-host", idempotency_key="wrong-host-key",
            expected_ledger_revision=app.progress_ledger.replay()["cursor"]["event_seq"])
        responses.append({"thread": {"id": "foreign", "cwd": str(self.codex_home)}})
        self.assertEqual(post(wrong_host)._json.call_args.args[1]["status"], "PENDING")
        self.assertEqual([fact["status"] for fact in app.progress_ledger.replay()["connector_receipts"]["wrong-host-key"]["receipts"]], ["COMMAND"])
        calls = len(sent)
        self.assertEqual(post(wrong_host)._json.call_args.args[1]["status"], "PENDING")
        self.assertEqual(len(sent), calls)
        self.assertEqual(app.progress_ledger.project_task_creation_bindings("project:alpha")["bindings"], binding["bindings"])

    def test_existing_task_message_http_retains_replay_and_never_reuses_old_turn(self) -> None:
        from contextlib import contextmanager
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE project_roots SET path=? WHERE project_id=?", (str(self.root), "project:alpha"))
            connection.execute("UPDATE threads SET cwd=? WHERE id='task'", (str(self.root),))
            connection.commit()
        app = console.App(self.codex_home, self.config)
        root = app._canonical_project_root("project:alpha")
        instruction = "Reply exactly SWARM_MESSAGE_PROBE_OK."
        now = int(time.time() * 1000)
        payload = {"acknowledge": True, "instruction": instruction, "envelope": {
            "command_id": "message-one", "idempotency_key": "message-key", "action": "TASK",
            "project_id": "project:alpha", "root_digest": console._auto_digest({"project_id": "project:alpha", "canonical_root": console._normalized_project_path(str(root))}),
            "ctrl_id": "", "target_intent": "EXISTING_THREAD", "target_thread_id": "task",
            "payload_digest": hashlib.sha256(instruction.encode()).hexdigest(), "expected_ledger_revision": 0,
            "submitted_at_ms": now, "expires_at_ms": now + 60000}}
        sent = []
        responses = [{"thread": {"id": "task", "cwd": str(root), "status": {"type": "idle"}}}, {"turn": {"id": "message-turn"}}]
        @contextmanager
        def session(cwd, **kwargs):
            self.assertEqual(cwd, root)
            def send(message):
                sent.append(message)
                if message["method"] == "thread/resume":
                    self.assertEqual(message["params"], {"threadId": "task"})
                else:
                    self.assertEqual(message["method"], "turn/start")
                    self.assertEqual(message["params"], {"threadId": "task", "cwd": str(root), "input": [{"type": "text", "text": instruction, "text_elements": []}]})
            yield send, lambda predicate: {"id": sent[-1]["id"], "result": responses.pop(0)}
        app.auto_bridge.command_session = session
        def post(body, token=None):
            handler = self._handler("127.0.0.1", "127.0.0.1:4788", token=app.token if token is None else token)
            handler.server.app = app
            handler.path = "/api/tasks/message"
            handler._payload = mock.Mock(return_value=body)
            handler._json = mock.Mock()
            handler._error = mock.Mock()
            handler.do_POST()
            return handler
        prepared = app.task_message_context({"project_id": "project:alpha", "thread_id": "task"})
        self.assertEqual(prepared["expected_ledger_revision"], payload["envelope"]["expected_ledger_revision"])
        for key, value in (("target_thread_id", "missing"), ("project_id", "foreign"), ("root_digest", "a"*64), ("payload_digest", "b"*64), ("ctrl_id", "invented"), ("expected_ledger_revision", 999)):
            bad = copy.deepcopy(payload)
            bad["envelope"][key] = value
            response = post(bad)
            self.assertTrue(response._error.called or response._json.call_args.args[1].get("status") == "CONFLICT")
        post(payload, token="wrong")._error.assert_called_once()
        self.assertEqual(sent, [])
        self.assertEqual(app.progress_ledger.replay()["connector_receipts"], {})
        result = post(payload)
        result._error.assert_not_called()
        result = result._json.call_args.args[1]
        self.assertEqual((result["status"], result["thread_id"], result["turn_id"]), ("RESULT", "task", "message-turn"))
        self.assertFalse(result["work_completed"])
        before = app.progress_ledger._state.path.read_bytes()
        self.assertNotIn(instruction.encode(), before)
        app = console.App(self.codex_home, self.config)
        app.auto_bridge.command_session = session
        self.assertEqual(post(payload)._json.call_args.args[1]["status"], "REPLAY")
        self.assertEqual(app.progress_ledger._state.path.read_bytes(), before)
        self.assertEqual(len(sent), 2)
        stale = copy.deepcopy(payload)
        stale["envelope"].update(command_id="stale-context", idempotency_key="stale-context", expected_ledger_revision=prepared["expected_ledger_revision"])
        stale_result = post(stale)
        rejection = stale_result._json.call_args.args[1]
        self.assertEqual(rejection["status"], "NOT_DISPATCHED")
        self.assertTrue(rejection["definitive_non_dispatch"])
        self.assertEqual(rejection["command_id"], "stale-context")
        fields = dict(stale["envelope"])
        fields["action"] = console.HQCommandAction(fields["action"])
        fields["target_intent"] = console.HQTargetIntent(fields["target_intent"])
        self.assertEqual(rejection["command_digest"], console.HQCommandEnvelope(**fields).digest)
        expired = copy.deepcopy(stale)
        expired["envelope"].update(command_id="expired-message", idempotency_key="expired-message", submitted_at_ms=now-120000, expires_at_ms=now-60000, expected_ledger_revision=app.progress_ledger.replay()["cursor"]["event_seq"])
        self.assertEqual(post(expired)._json.call_args.args[1]["status"], "NOT_DISPATCHED")
        conflicting = copy.deepcopy(stale)
        conflicting["envelope"]["command_id"] = payload["envelope"]["command_id"]
        post(conflicting)._error.assert_called_once()
        self.assertEqual(len(sent), 2)
        self.assertEqual(app.progress_ledger._state.path.read_bytes(), before)
        for name, reply in (("active", {"thread": {"id": "task", "cwd": str(root), "status": {"type": "active"}}}),
                            ("wrong-root", {"thread": {"id": "task", "cwd": str(self.codex_home), "status": {"type": "idle"}}}),
                            ("unknown-state", {"thread": {"id": "task", "cwd": str(root)}})):
            bad = copy.deepcopy(payload)
            bad["envelope"].update(command_id=name, idempotency_key=name, expected_ledger_revision=app.progress_ledger.replay()["cursor"]["event_seq"])
            responses.append(reply)
            calls = len(sent)
            pending = post(bad)._json.call_args.args[1]
            self.assertEqual(pending["status"], "NOT_DISPATCHED" if name == "active" else "PENDING")
            self.assertFalse(pending["work_completed"])
            self.assertEqual(len(sent), calls+1)
            if name == "active":
                before_busy = app.progress_ledger._state.path.read_bytes()
                app = console.App(self.codex_home, self.config)
                app.auto_bridge.command_session = session
                self.assertEqual(post(bad)._json.call_args.args[1], pending)
                self.assertEqual(len(sent), calls+1)
                self.assertEqual(app.progress_ledger._state.path.read_bytes(), before_busy)
                fresh = copy.deepcopy(payload)
                fresh["envelope"].update(command_id="fresh-after-busy", idempotency_key="fresh-after-busy", expected_ledger_revision=app.progress_ledger.replay()["cursor"]["event_seq"])
                responses.extend([{"thread": {"id": "task", "cwd": str(root), "status": {"type": "idle"}}}, {"turn": {"id": "fresh-turn"}}])
                self.assertEqual(post(fresh)._json.call_args.args[1]["status"], "RESULT")
                self.assertEqual(len(sent), calls+3)
        uncertain = copy.deepcopy(payload)
        uncertain["envelope"].update(command_id="uncertain-message", idempotency_key="uncertain-message", expected_ledger_revision=app.progress_ledger.replay()["cursor"]["event_seq"])
        responses.extend([{"thread": {"id": "task", "cwd": str(root), "status": {"type": "idle"}}}, {}])
        self.assertEqual(post(uncertain)._json.call_args.args[1]["status"], "PENDING")
        self.assertNotIn("definitive_non_dispatch", post(uncertain)._json.call_args.args[1])
        before = app.progress_ledger._state.path.read_bytes()
        calls = len(sent)
        app = console.App(self.codex_home, self.config)
        app.auto_bridge.command_session = session
        self.assertEqual(post(uncertain)._json.call_args.args[1]["status"], "PENDING")
        self.assertEqual(len(sent), calls, "uncertain existing message cannot be mistaken for a historical turn or resent")
        self.assertEqual(app.progress_ledger._state.path.read_bytes(), before)

    def test_task_message_context_is_exact_read_only_preparation(self) -> None:
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE project_roots SET path=? WHERE project_id=?", (str(self.root), "project:alpha"))
            connection.execute("UPDATE threads SET cwd=? WHERE id='task'", (str(self.root),))
            connection.commit()
        app = console.App(self.codex_home, self.config)
        def post(body, token=None):
            handler = self._handler("127.0.0.1", "127.0.0.1:4788", token=app.token if token is None else token)
            handler.server.app = app
            handler.path = "/api/tasks/message-context"
            handler._payload = mock.Mock(return_value=body)
            handler._json = mock.Mock()
            handler._error = mock.Mock()
            handler.do_POST()
            return handler
        payload = {"project_id": "project:alpha", "thread_id": "task"}
        before = app.progress_ledger.replay()
        with mock.patch.object(app.auto_bridge, "command_session", side_effect=AssertionError("context must not dispatch")):
            response = post(payload)
        response._error.assert_not_called()
        context = response._json.call_args.args[1]
        self.assertEqual(context["project_id"], "project:alpha")
        self.assertEqual(context["target_thread_id"], "task")
        self.assertEqual(context["root_digest"], console._auto_digest({"project_id": "project:alpha", "canonical_root": console._normalized_project_path(str(self.root.resolve()))}))
        self.assertEqual(context["expected_ledger_revision"], before["cursor"]["event_seq"])
        self.assertEqual(context["expires_at_ms"] - context["submitted_at_ms"], 60000)
        self.assertEqual((context["action"], context["target_intent"], context["ctrl_id"]), ("TASK", "EXISTING_THREAD", ""))
        self.assertNotIn("command_id", context)
        self.assertNotIn("instruction", context)
        self.assertEqual(app.progress_ledger.replay(), before)
        post(payload, token="wrong")._error.assert_called_once()
        post({**payload, "project_id": "foreign"})._error.assert_called_once()
        post({**payload, "thread_id": "missing"})._error.assert_called_once()
        with mock.patch.object(app, "_observed_task_root", side_effect=[self.root, self.codex_home]):
            post(payload)._error.assert_called_once()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE threads SET archived=1 WHERE id='task'")
            connection.commit()
        post(payload)._error.assert_called_once()
        handler = self._handler("127.0.0.1", "127.0.0.1:4788", token=app.token)
        handler.server.app = app
        capability = handler._bootstrap_payload()["capabilities"]["task_message"]
        self.assertEqual(capability["endpoint"], "/api/tasks/message")
        self.assertEqual(capability["context_endpoint"], "/api/tasks/message-context")
        self.assertNotIn("hq_connector", handler._bootstrap_payload()["capabilities"])
        remote = self._handler("203.0.113.1", "127.0.0.1:4788", token=app.token)
        remote.server.app = app
        self.assertEqual(remote._bootstrap_payload()["capabilities"], {})

    def test_importlib_loaded_server_can_import_packaged_console_siblings(self) -> None:
        self.assertIn(str(console.CONSOLE_ROOT), sys.path)
        self.assertEqual(console.ConsoleStore(self.root / "console" / "importlib.sqlite3").skill_catalog()[0]["skill_id"], "find-skills")

    def test_health_identity_is_bound_to_the_console_root(self) -> None:
        self.assertEqual(len(console.INSTANCE_ID), 16)
        self.assertRegex(console.INSTANCE_ID, r"^[0-9a-f]+$")
        expected_build_id = hashlib.sha256(SERVER.read_bytes()).hexdigest()[:16]
        self.assertEqual(console.SERVER_BUILD_ID, expected_build_id)
        handler = self._handler("127.0.0.1", "127.0.0.1:4788")
        handler.path = "/healthz"
        handler._json = mock.Mock()
        handler.do_GET()
        handler._json.assert_called_once_with(console.HTTPStatus.OK, {
            "ok": True,
            "service": "swarm-console",
            "instance_id": console.INSTANCE_ID,
            "build_id": expected_build_id,
        })

    def test_lab_catalog_is_read_only_and_role_bound(self) -> None:
        app = console.App(self.codex_home, self.config)
        projection = app.lab_catalog_projection()
        self.assertEqual([lab["id"] for lab in projection["labs"]], ["strategy", "build", "growth", "design"])
        self.assertTrue(projection["read_only"])
        role_ids = {role["id"] for role in app.role_manifest_projection()["roles"]}
        self.assertTrue(all(set(lab["role_ids"]).issubset(role_ids) for lab in projection["labs"]))
        self.assertIn('if path == "/api/labs":', SERVER.read_text(encoding="utf-8"))

    def test_role_manifest_http_contract_is_server_owned_and_asset_bound(self) -> None:
        app = console.App(self.codex_home, self.config)
        projection = app.role_manifest_projection()
        self.assertTrue(projection["ok"])
        self.assertEqual((projection["built_in_count"], len(projection["roles"])), (24, 24))
        self.assertEqual(projection["command_contract"]["endpoint"], "/api/role-manifests/commands")
        self.assertEqual(projection["hierarchy_binding"]["levels"], ["PROJECT", "CTRL", "LEAD", "DOER"])
        manager = next(role for role in projection["roles"] if role["id"] == "manager")
        self.assertEqual(manager["avatar"], {
            "state": "AVAILABLE",
            "digest": manager["avatar_asset_digest"],
            "url": "/assets/role-avatars/manager.png",
        })
        png = app.role_avatar_response("manager", "image/png")
        webp = app.role_avatar_response("manager", "image/webp,image/*")
        avif = app.role_avatar_response("manager", "image/avif,image/webp")
        rejected_avif = app.role_avatar_response("manager", "image/avif;q=0,image/webp")
        preferred_webp = app.role_avatar_response("manager", "image/avif;q=.4,image/webp;q=.9")
        wildcard_rejected_avif = app.role_avatar_response("manager", "image/*;q=1,image/avif;q=0")
        global_wildcard_rejected_avif = app.role_avatar_response("manager", "*/*;q=1,image/avif;q=0")
        self.assertEqual((png["media_type"], png["body"][:8]), ("image/png", b"\x89PNG\r\n\x1a\n"))
        self.assertEqual((webp["media_type"], webp["body"][:4]), ("image/webp", b"RIFF"))
        self.assertEqual(avif["media_type"], "image/avif")
        self.assertEqual((rejected_avif["media_type"], preferred_webp["media_type"]), ("image/webp", "image/webp"))
        self.assertEqual(
            (wildcard_rejected_avif["media_type"], global_wildcard_rejected_avif["media_type"]),
            ("image/webp", "image/webp"),
        )
        self.assertIn(b"ftypavif", avif["body"][:32])
        self.assertLess(len(avif["body"]), len(png["body"]))
        with self.assertRaisesRegex(console.ConsoleError, "not found"):
            app.role_avatar_response("unknown", "image/avif")
        with self.assertRaisesRegex(console.NotAcceptableError, "no acceptable"):
            app.role_avatar_response("manager", "image/avif;q=0,image/webp;q=0,image/png;q=0")
        draft = {key: manager[key] for key in (
            "name", "purpose", "owns", "instructions", "boundaries",
            "default_skills", "specializations", "avatar_asset_digest", "accent",
        )}
        request = {
            "command": "ROLE_MANIFEST_REVISE",
            "role_id": "manager",
            "event_id": "manager-http-revision",
            "dedupe_key": "manager-http-revision-dedupe",
            "expected_active_version": manager["active_version"],
            "manifest": {**draft, "accent": "#123456"},
            "provenance": "localhost-command:manager-http-revision",
            "observed_at_ms": 10,
        }
        first = app.role_manifest_command(request)
        self.assertEqual(first["receipt"]["status"], "appended")
        self.assertRegex(first["receipt"]["event_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(app.role_manifest_command(request)["receipt"]["status"], "unchanged")
        revised = next(role for role in first["projection"]["roles"] if role["id"] == "manager")
        self.assertTrue(revised["override_active"])

        with self.assertRaisesRegex(console.ConsoleError, "immutable Assets storage"):
            app.role_manifest_command({
                "command": "ROLE_MANIFEST_CREATE",
                "role_id": "custom-release-guide",
                "event_id": "custom-release-guide-create",
                "dedupe_key": "custom-release-guide-create-dedupe",
                "expected_active_version": None,
                "manifest": {**draft, "name": "Release Guide", "avatar_asset_digest": "0" * 64},
                "provenance": "localhost-command:custom-release-guide",
                "observed_at_ms": 11,
            })
        source = SERVER.read_text(encoding="utf-8")
        self.assertIn('if path == "/api/role-manifests":', source)
        self.assertIn('if path == "/api/role-manifests/commands":', source)

    def test_role_avatar_reparse_paths_fail_closed(self) -> None:
        app = console.App(self.codex_home, self.config)
        root = self.codex_home / console.PROOF_MEDIA_ROOT
        root.mkdir(parents=True)
        digest = "a" * 64
        candidate = root / f"{digest}.png"
        candidate.write_bytes(b"not-read-after-reparse-rejection")

        with mock.patch.object(
            Path, "lstat", return_value=SimpleNamespace(st_file_attributes=0x400)
        ), mock.patch.object(Path, "is_symlink", return_value=False):
            self.assertTrue(console._is_reparse_point(root))

        with self.subTest(path="root"), mock.patch.object(
            console, "_is_reparse_point", side_effect=lambda path: path == root
        ):
            with self.assertRaisesRegex(console.ConsoleError, "immutable Assets storage"):
                app._require_role_avatar(digest)

        with self.subTest(path="candidate-before-containment"), mock.patch.object(
            console, "_is_reparse_point", side_effect=lambda path: path == candidate
        ):
            with self.assertRaisesRegex(console.ConsoleError, "immutable Assets storage"):
                app._require_role_avatar(digest)

        candidate_checks = 0

        def reparse_after_containment(path: Path) -> bool:
            nonlocal candidate_checks
            if path == candidate:
                candidate_checks += 1
                return candidate_checks == 2
            return False

        with self.subTest(path="candidate-after-containment"), mock.patch.object(
            console, "_is_reparse_point", side_effect=reparse_after_containment
        ):
            with self.assertRaisesRegex(console.ConsoleError, "immutable Assets storage"):
                app._require_role_avatar(digest)
        self.assertEqual(candidate_checks, 2)

    def test_duplicate_role_create_is_http_conflict(self) -> None:
        app = console.App(self.codex_home, self.config)
        manager = next(role for role in app.role_manifest_projection()["roles"] if role["id"] == "manager")
        draft = {key: manager[key] for key in (
            "name", "purpose", "owns", "instructions", "boundaries",
            "default_skills", "specializations", "avatar_asset_digest", "accent",
        )}
        create = {
            "command": "ROLE_MANIFEST_CREATE",
            "role_id": "custom-release-guide",
            "event_id": "custom-release-guide-create",
            "dedupe_key": "custom-release-guide-create-dedupe",
            "expected_active_version": None,
            "manifest": {**draft, "name": "Release Guide"},
            "provenance": "localhost-command:custom-release-guide",
            "observed_at_ms": 11,
        }
        self.assertEqual(app.role_manifest_command(create)["receipt"]["status"], "appended")
        duplicate = {
            **create,
            "event_id": "custom-release-guide-create-again",
            "dedupe_key": "custom-release-guide-create-again-dedupe",
            "observed_at_ms": 12,
        }
        with self.assertRaisesRegex(console.ConsoleConflict, "cannot replace an existing role"):
            app.role_manifest_command(duplicate)

        handler = self._handler("127.0.0.1", "127.0.0.1:4788", token=app.token)
        handler.server = SimpleNamespace(app=app)
        handler.path = "/api/role-manifests/commands"
        handler._payload = mock.Mock(return_value=duplicate)
        handler._json = mock.Mock()
        handler.do_POST()
        handler._json.assert_called_once_with(
            console.HTTPStatus.CONFLICT,
            {"ok": False, "error": "role manifest create cannot replace an existing role"},
        )

    def test_critic_role_commands_fail_closed_while_history_remains_readable(self) -> None:
        app = console.App(self.codex_home, self.config)
        projection = app.role_manifest_projection()
        assistant = next(role for role in projection["roles"] if role["id"] == "assistant")
        draft = {key: assistant[key] for key in (
            "name", "purpose", "owns", "instructions", "boundaries",
            "default_skills", "specializations", "avatar_asset_digest", "accent",
        )}
        ledger_path = app.progress_ledger._state.path

        def ledger_bytes() -> bytes:
            return ledger_path.read_bytes() if ledger_path.exists() else b""

        for index, role_id in enumerate(("critic", " CrItIc "), start=1):
            before = ledger_bytes()
            with self.subTest(command="create", role_id=role_id), self.assertRaisesRegex(
                console.ConsoleError, "retained as history"
            ):
                app.role_manifest_command({
                    "command": "ROLE_MANIFEST_CREATE",
                    "role_id": role_id,
                    "event_id": f"critic-create-{index}",
                    "dedupe_key": f"critic-create-{index}-dedupe",
                    "expected_active_version": None,
                    "manifest": {**draft, "name": "Critic"},
                    "provenance": "localhost-command:critic-create",
                    "observed_at_ms": index,
                })
            self.assertEqual(ledger_bytes(), before)

        historical = console.build_role_manifest(
            "critic",
            {
                **draft,
                "name": "Critic",
                "purpose": "Decode one retained historical role revision.",
                "boundaries": ["No current routing or review authority."],
                "specializations": [],
            },
            "custom",
            ["history:critic:v1"],
        )
        app.progress_ledger.append(console.role_material_event(
            "ROLE_MANIFEST_CREATE",
            event_id="historical-critic",
            dedupe_key="historical-critic-dedupe",
            role_id="critic",
            manifest=historical,
            expected_active_version=None,
            assignment_task_id=None,
            provenance="history:critic:v1",
            observed_at_ms=10,
        ))
        retained = next(role for role in app.role_manifest_projection()["roles"] if role["id"] == "critic")
        self.assertFalse(retained["built_in"])
        self.assertEqual(retained["active_version"], historical["version"])

        for index, role_id in enumerate(("critic", "CrItIc"), start=11):
            before = ledger_bytes()
            with self.subTest(command="revise", role_id=role_id), self.assertRaisesRegex(
                console.ConsoleError, "retained as history"
            ):
                app.role_manifest_command({
                    "command": "ROLE_MANIFEST_REVISE",
                    "role_id": role_id,
                    "event_id": f"critic-revise-{index}",
                    "dedupe_key": f"critic-revise-{index}-dedupe",
                    "expected_active_version": historical["version"],
                    "manifest": {**draft, "name": "Critic revised"},
                    "provenance": "localhost-command:critic-revise",
                    "observed_at_ms": index,
                })
            self.assertEqual(ledger_bytes(), before)

        valid = app.role_manifest_command({
            "command": "ROLE_MANIFEST_CREATE",
            "role_id": "custom-assistant-helper",
            "event_id": "custom-assistant-helper-create",
            "dedupe_key": "custom-assistant-helper-create-dedupe",
            "expected_active_version": None,
            "manifest": {**draft, "name": "Assistant helper", "specializations": []},
            "provenance": "localhost-command:custom-assistant-helper",
            "observed_at_ms": 20,
        })
        self.assertEqual(valid["receipt"]["status"], "appended")
        current_ids = {role["id"] for role in valid["projection"]["roles"]}
        self.assertIn("assistant", current_ids)
        self.assertIn("custom-assistant-helper", current_ids)

    def test_new_console_copy_is_swarm_first(self) -> None:
        static = (Path(__file__).resolve().parents[1] / "static")
        index = (static / "index.html").read_text(encoding="utf-8")
        app = (static / "app.js").read_text(encoding="utf-8")
        self.assertIn('src="/assets/swarm-wordmark.png"', index)
        for view in ("overview", "agents", "roles", "review", "assets", "diagnostics", "settings"):
            self.assertIn(f'id="tab-{view}"', index)
            self.assertIn(f'id="view-{view}"', index)
        for retired in ("hierarchy", "kanban"):
            self.assertNotIn(f'id="tab-{retired}"', index)
        self.assertIn('id="project-navigation"', index)
        self.assertIn('id="scope-context"', index)
        self.assertIn("function renderProjectNavigation()", app)
        self.assertIn("function renderAgents()", app)
        self.assertIn("function renderReview()", app)
        self.assertIn("function renderAssets()", app)
        self.assertIn("function renderSettings()", app)
        self.assertIn("function authoritativeProgress(projectId, ctrlId", app)
        self.assertIn('validPercent == null ? "Unmeasured"', app)
        self.assertNotIn("completed / total", app)
        self.assertNotIn("progress_basis?.percent", app)
        self.assertIn('id="sync-time" role="status" aria-live="polite">Reconnecting', index)
        self.assertIn('id="snapshot-status-dot"', index)
        self.assertIn('id="sync-time" role="status" aria-live="polite"', index)
        self.assertNotIn("Projects are up to date", index)
        self.assertIn('setDataStatus("current", state.overview?.generated_at)', app)
        self.assertIn('setDataStatus(state.overview ? "stale" : "unavailable"', app)
        self.assertIn('api(overviewRequestPath(), { timeoutMs: 15_000 })', app)
        self.assertIn("function publicLabel(value", app)
        self.assertIn(r'.replace(/\blocalhost\b/gi, "console")', app)
        self.assertIn('const label = rawLabel.localeCompare(group.label', app)
        self.assertIn("if (!group.standalone) options.push", app)
        self.assertIn('id="diagnostics-health-heading">Checking health</h3>', index)
        self.assertNotIn("localhost", index.casefold())
        self.assertNotIn("hidden usage", index.casefold())
        self.assertNotIn("do not consume task or model usage", index.casefold())
        self.assertNotIn("Awaiting v3 direction", index)
        self.assertNotIn('id="controller-filter"', index)
        self.assertNotIn('aria-label="Graph"', index)
        self.assertEqual(index.count('id="view-title"'), 1)

    def test_wordmark_uses_exact_existing_asset_route(self) -> None:
        asset, content_type = console.STATIC_ASSETS["/assets/swarm-wordmark.png"]
        self.assertEqual(asset, console.PLUGIN_ROOT / "skills" / "swarm" / "assets" / "swarm-wordmark.png")
        self.assertEqual(content_type, "image/png")
        self.assertTrue(asset.is_file())
        self.assertGreater(asset.stat().st_size, 100_000)

    def test_console_uses_selected_compact_swarm_icon_not_wordmark(self) -> None:
        index = (console.STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        icon = (console.STATIC_ROOT / "swarm-icon-64.png").read_bytes()
        mascot = (console.STATIC_ROOT / "swarm-mascot-512.png").read_bytes()
        self.assertIn('<link rel="icon" type="image/png" sizes="64x64" href="/swarm-icon-64.png" />', index)
        self.assertNotIn('rel="icon" href="/assets/swarm-wordmark.png"', index)
        self.assertEqual(console.STATIC_FILES["/swarm-icon-64.png"], ("swarm-icon-64.png", "image/png"))
        self.assertEqual(console.STATIC_FILES["/assets/swarm-mascot-512.png"], ("swarm-mascot-512.png", "image/png"))
        self.assertEqual(
            console.STATIC_FILES["/assets/swarm-state-mascot-concerned.png"],
            ("swarm-state-mascot-concerned.png", "image/png"),
        )
        self.assertEqual(icon[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual((int.from_bytes(icon[16:20], "big"), int.from_bytes(icon[20:24], "big")), (64, 64))
        self.assertEqual(mascot[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual((int.from_bytes(mascot[16:20], "big"), int.from_bytes(mascot[20:24], "big")), (512, 512))

    def test_console_exposes_state_mascot_webp_routes(self) -> None:
        self.assertEqual(
            console.STATIC_FILES["/assets/swarm-offline-disconnected.webp"],
            ("swarm-offline-disconnected.webp", "image/webp"),
        )
        self.assertEqual(
            console.STATIC_FILES["/assets/swarm-state-mascot-concerned.webp"],
            ("swarm-state-mascot-concerned.webp", "image/webp"),
        )
        self.assertEqual(
            console.STATIC_FILES["/assets/support-caricature-light.webp"],
            ("support-caricature-light.webp", "image/webp"),
        )

    def test_console_uses_flowwweb_swarm_tokens_without_lime_controls(self) -> None:
        css = (console.STATIC_ROOT / "styles.css").read_text(encoding="utf-8").casefold()
        index = (console.STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        for token in ("#091321", "#46dfd0", "#ff7a18"):
            self.assertIn(token, css)
        for stale in ("#a8ff4f", "168,255,79", "#8ef2c2"):
            self.assertNotIn(stale, css)
        self.assertIn(".toggle-row input", css)
        self.assertIn("accent-color:var(--cyan)", css)
        self.assertIn("<h2>One goal. A coordinated team.</h2>", index)
        for removed in ("RAPID UNIFIED", "LIVE HIERARCHY", "Observed pulse"):
            self.assertNotIn(removed, index)
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.codex_home = self.root / "codex"
        self.codex_home.mkdir()
        self.config = self.root / "swarm" / "config.toml"
        self.config.parent.mkdir()
        source = console.PLUGIN_ROOT / "skills" / "swarm" / "assets" / "swarm-config.toml"
        self.config.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        self.database = self.codex_home / "state_5.sqlite"
        self.connection = sqlite3.connect(self.database)
        self.connection.executescript(
            """
            CREATE TABLE threads (
              id TEXT PRIMARY KEY, title TEXT, cwd TEXT, created_at INTEGER,
              updated_at INTEGER, created_at_ms INTEGER, updated_at_ms INTEGER,
              model TEXT, reasoning_effort TEXT, tokens_used INTEGER, archived INTEGER,
              git_origin_url TEXT, git_branch TEXT, thread_source TEXT,
              agent_nickname TEXT, agent_role TEXT, is_pinned INTEGER
            );
            CREATE TABLE thread_spawn_edges (
              parent_thread_id TEXT, child_thread_id TEXT, status TEXT
            );
            CREATE TABLE projects (
              id TEXT PRIMARY KEY, name TEXT, metadata TEXT, position INTEGER,
              created_at_ms INTEGER, updated_at_ms INTEGER
            );
            CREATE TABLE project_roots (
              project_id TEXT, position INTEGER, path TEXT
            );
            """
        )
        self.connection.execute(
            "INSERT INTO projects VALUES (?,?,?,?,?,?)",
            ("project:alpha", "alpha", "{}", 0, 0, 0),
        )
        self.connection.execute(
            "INSERT INTO project_roots VALUES (?,?,?)",
            ("project:alpha", 0, "C:/work/alpha"),
        )
        now = 2_000_000_000_000
        rows = [
            ("root", "🐙CTRL - Ship console", "C:/work/alpha", now, now, "gpt-5.6-sol", "high", 100),
            ("lead", "🧭LEAD - Console", "C:/work/alpha", now, now, "gpt-5.6-terra", "medium", 200),
            ("task", "🔨DEV - Local API", "C:/work/alpha", now, now, "gpt-5.6-luna", "xhigh", 300),
            ("review", "🔍REVIEW - Console proof", "C:/work/alpha", now, now, "gpt-5.6-sol", "high", 150),
            ("unsafe", "Please do this\nwith secret prompt text", "C:/private/path", now, now, "gpt", "low", 999),
        ]
        for thread_id, title, cwd, created, updated, model, effort, tokens in rows:
            self.connection.execute(
                "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (thread_id, title, cwd, created // 1000, updated // 1000, created, updated,
                 model, effort, tokens, 0, "", "main", "", "", "", 0),
            )
        self.connection.executemany(
            "INSERT INTO thread_spawn_edges VALUES (?,?,?)",
            [("root", "lead", "open"), ("lead", "task", "open"), ("lead", "review", "closed")],
        )
        self.connection.commit()
        self.connection.close()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _add_host_project(self, project_id: str, name: str, root: str) -> None:
        connection = sqlite3.connect(self.database)
        connection.execute(
            "INSERT INTO projects VALUES (?,?,?,?,?,?)",
            (project_id, name, "{}", 0, 0, 0),
        )
        connection.execute(
            "INSERT INTO project_roots VALUES (?,?,?)",
            (project_id, 0, root),
        )
        connection.commit()
        connection.close()

    def _confirm_root_ctrl(self) -> None:
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE threads SET agent_role = 'ctrl' WHERE id = 'root'")
            connection.commit()

    def _append_topology_manifests(
        self, app: console.App, *, task_count: int = 4, include_review: bool = False,
    ) -> None:
        roles = {manifest["id"]: manifest for manifest in app.builtin_role_manifests}
        agents = [
            ("root", "CTRL", "SWARM HQ", "manager", "CTRL"),
            ("lead", "Cobalt", "Delivery lane", "developer", "LEAD"),
            ("task", "Mint", "Implementation lane", "tester", "DOER"),
        ]
        if include_review:
            agents.append(("review", "Rose", "Review lane", "reviewer", "DOER"))
        for index, (agent_id, display_name, title, profession, structural_role) in enumerate(agents, 1):
            manifest = build_agent_manifest(
                manifest_id=f"agent-manifest:{agent_id}", agent_id=agent_id,
                project_id="project:alpha", ctrl_id="root", display_name=display_name,
                title=title, profession=profession, structural_role=structural_role,
                avatar_selection="canonical", role_manifest_ref=role_manifest_reference(roles[profession]),
            )
            app.progress_ledger.append(identity_manifest_event(
                manifest, event_id=f"agent-manifest-{index}", dedupe_key=f"agent-manifest-{index}-dedupe",
                observed_at_ms=index, provenance="console topology fixture",
            ))
        priorities = (30, 10, 20, 40)
        for index in range(task_count):
            task_id, block_id, milestone_id = f"work-{index + 1}", f"work-block-{index + 1}", f"work-milestone-{index + 1}"
            manifest = build_task_manifest(
                manifest_id=f"task-manifest:{task_id}", task_id=task_id,
                task_name=f"Manifest task {index + 1}", project_id="project:alpha", ctrl_id="root",
                policy={
                    "presentation_priority": priorities[index], "weighted_progress": False,
                    "expected_update_interval_minutes": 30, "amber_freshness_multiplier": 2,
                    "red_freshness_multiplier": 4, "amber_estimate_ratio_milli": 1000,
                    "red_estimate_ratio_milli": 1500,
                },
                milestones=[{
                    "milestone_id": milestone_id, "order": 0, "title": "Active work",
                    "verification_policy": "source-contract", "supersedes_milestone_id": None,
                }],
                blocks=[{
                    "block_id": block_id, "milestone_id": milestone_id, "order": 0,
                    "title": "Do the work", "verification_policy": "source-contract",
                    "estimate_minutes": None, "weight": None, "supersedes_block_id": None,
                }],
            )
            app.progress_ledger.append(identity_manifest_event(
                manifest, event_id=f"task-manifest-{index + 1}",
                dedupe_key=f"task-manifest-{index + 1}-dedupe",
                observed_at_ms=10 + index, provenance="console topology fixture",
            ))
            event = self._notification_event(
                f"work-event-{index + 1}", block_id, "BLOCK_CREATED", "ACTIVE", 100 + index,
                milestone_id=milestone_id,
            )
            event.update(task_id=task_id, owner_id="root", ctrl_id="root")
            app.progress_ledger.append(event)

    def _asset_generation_payload(
        self,
        asset_id: str = "asset-dashboard-a",
        *,
        logical_asset_id: str = "logical-dashboard",
        parent_revision_id: str | None = None,
        operation_id: str = "generation-op-a",
        generation_job_id: str = "generation-job-a",
        idempotency_key: str = "generation-request-a",
    ) -> dict[str, object]:
        return {
            "project_id": "project:alpha",
            "asset_id": asset_id,
            "logical_asset_id": logical_asset_id,
            "parent_revision_id": parent_revision_id,
            "generation_job_id": generation_job_id,
            "operation_id": operation_id,
            "idempotency_key": idempotency_key,
            "request_summary": "Render dashboard mockup",
            "presentation": {
                "display_name": "Dashboard mockup",
                "kind": "mockup",
                "description": "A reviewable dashboard option.",
            },
            "job_metadata": {"mode": "draft", "option": "a"},
            "provenance": {"source": "user-action", "receipt": "asset-request-a"},
        }

    def _add_same_project_ctrl(self) -> None:
        now = 2_000_000_100_000
        with closing(sqlite3.connect(self.database)) as connection:
            connection.executemany(
                "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        "other-ctrl", "🐙CTRL - Other", "C:/work/alpha", now // 1000,
                        now // 1000, now, now, "gpt-5.6-sol", "high", 1, 0, "", "main",
                        "", "", "ctrl", 0,
                    ),
                    (
                        "other-task", "🔨DEV - Other", "C:/work/alpha", now // 1000,
                        now // 1000, now, now, "gpt-5.6-luna", "medium", 1, 0, "", "main",
                        "", "", "", 0,
                    ),
                ],
            )
            connection.execute(
                "INSERT INTO thread_spawn_edges VALUES (?,?,?)",
                ("other-ctrl", "other-task", "open"),
            )
            connection.commit()

    @staticmethod
    def _write_project_brief(
        root: Path,
        project_id: str,
        *,
        links: list[dict[str, object]] | None = None,
        proposed_lens_ids: list[str] | None = None,
        extra: dict[str, object] | None = None,
    ) -> None:
        root.mkdir(parents=True, exist_ok=True)
        brief = {
            "schema_version": 1,
            "updated_at": "2026-08-30T00:00:00Z",
            "project": {"id": project_id, "purpose": "A bounded saved project fixture."},
            "users_outcomes": [],
            "objective": {},
            "repo": {},
            "authority": {},
            "milestones": [],
            "decisions": [],
            "ownership": {},
            "proof_acceptance": {},
            "risks_blockers": [],
            "links": links or [],
        }
        if proposed_lens_ids is not None:
            brief["proposed_lens_ids"] = proposed_lens_ids
        brief.update(extra or {})
        root.joinpath("SWARM.md").write_text(
            "<!-- swarm-project-brief:schema=1 -->\n"
            "```json\n"
            + json.dumps(brief, sort_keys=True)
            + "\n```\n",
            encoding="utf-8",
        )

    @staticmethod
    def _notification_event(
        event_id: str, block_id: str, event_kind: str, lifecycle_state: str,
        observed_at_ms: int, *, parent_event_id: str | None = None,
        admitted_proof_weight: int = 0, proof_receipt_ids: list[str] | None = None,
        proof_required_classes: list[str] | None = None, flags: list[str] | None = None,
        milestone_id: str = "milestone-one", committed_weight: int = 1,
    ) -> dict[str, object]:
        proof_receipt_ids = proof_receipt_ids or []
        return {
            "schema_version": 1,
            "event_id": event_id,
            "dedupe_key": f"{event_id}-dedupe",
            "portfolio_id": "portfolio-main",
            "project_id": "project:alpha",
            "ctrl_id": "root",
            "milestone_id": milestone_id,
            "block_id": block_id,
            "task_id": "task",
            "owner_id": "owner-task",
            "scope_version": 1,
            "parent_block_id": None,
            "dependency_ids": [],
            "lineage": {"predecessor_block_ids": [], "split_from": None, "merged_from": []},
            "event_kind": event_kind,
            "lifecycle_state": lifecycle_state,
            "measurement": {
                "state": "MEASURED", "committed_weight": committed_weight,
                "admitted_proof_weight": admitted_proof_weight,
                "basis_receipt_ids": [f"weight-{block_id}"],
            },
            "proof": {
                "required_classes": proof_required_classes or ["SOURCE"], "receipt_ids": proof_receipt_ids,
                "claim_limit": "Source proof only.",
            },
            "eta": {"start_ms": None, "end_ms": None, "confidence": None, "basis_receipt_ids": []},
            "rework": {"attempt": 1, "count": 0, "invalidated_receipt_ids": []},
            "custody": {"surface": f"surface:{block_id}", "receipt_id": f"custody-{block_id}"},
            "steering_receipt_ids": [],
            "material_update_sentence": None,
            "flags": flags or [],
            "provenance": "typed owner material boundary",
            "source": "swarm_runtime",
            "observed_at_ms": observed_at_ms,
            "causation_id": None,
            "parent_event_id": parent_event_id,
        }

    @classmethod
    def _compact_blocker_event(cls, index: int) -> dict[str, object]:
        suffix = format(index, "x")
        event = cls._notification_event(
            suffix, "b", "BLOCK_CREATED", "WAITING_EXTERNAL", 1,
            flags=["blocked"], milestone_id="m",
        )
        event.update(
            portfolio_id="p", project_id="p", ctrl_id="c", task_id="t",
            owner_id="o", provenance="p", dedupe_key=suffix,
        )
        event["measurement"] = {
            "state": "UNMEASURED", "committed_weight": None,
            "admitted_proof_weight": 0, "basis_receipt_ids": [],
        }
        event["proof"] = {"required_classes": [], "receipt_ids": [], "claim_limit": "x"}
        event["custody"] = {"surface": "s", "receipt_id": "c"}
        return event

    def _append_notification_fixture(self, app: console.App) -> None:
        events = [
            self._notification_event(
                "blocker-created", "blocked-block", "BLOCK_CREATED", "WAITING_EXTERNAL", 10,
                flags=["blocked", "waiting_external"],
            ),
            self._notification_event("review-created", "review-block", "BLOCK_CREATED", "ACTIVE", 20),
            self._notification_event(
                "review-requested", "review-block", "STATE_CHANGED", "REVIEW", 21,
                parent_event_id="review-created", proof_required_classes=["INDEPENDENT_REVIEW"],
            ),
            self._notification_event(
                "generic-source-proof", "review-block", "PROOF_ADMITTED", "VERIFIED", 22,
                parent_event_id="review-requested", admitted_proof_weight=1,
                proof_receipt_ids=["source-proof"],
            ),
            self._notification_event(
                "review-completed", "review-block", "PROOF_ADMITTED", "VERIFIED", 23,
                parent_event_id="review-requested", admitted_proof_weight=1,
                proof_receipt_ids=["independent-review-proof"],
                proof_required_classes=["INDEPENDENT_REVIEW"],
            ),
            self._notification_event(
                "accepted-block", "review-block", "ACCEPTED", "ACCEPTED", 24,
                parent_event_id="review-completed", admitted_proof_weight=1,
                proof_receipt_ids=["independent-review-proof", "acceptance-proof"],
            ),
            self._notification_event(
                "milestone-created", "milestone-one", "BLOCK_CREATED", "ACTIVE", 24,
            ),
            self._notification_event(
                "milestone-review", "milestone-one", "STATE_CHANGED", "REVIEW", 25,
                parent_event_id="milestone-created",
            ),
            self._notification_event(
                "milestone-proof", "milestone-one", "PROOF_ADMITTED", "VERIFIED", 26,
                parent_event_id="milestone-review", admitted_proof_weight=1,
                proof_receipt_ids=["milestone-acceptance-proof"],
                proof_required_classes=["MILESTONE_ACCEPTANCE"],
            ),
            self._notification_event(
                "milestone-completed", "milestone-one", "ACCEPTED", "ACCEPTED", 27,
                parent_event_id="milestone-proof",
                admitted_proof_weight=1, proof_receipt_ids=["milestone-acceptance-proof"],
                proof_required_classes=["MILESTONE_ACCEPTANCE"],
            ),
            self._notification_event("ordinary-progress", "ordinary-block", "BLOCK_CREATED", "ACTIVE", 30),
        ]
        for event in events:
            self.assertEqual(app.progress_ledger.append(event)["status"], "appended")

    @classmethod
    def _progress_queue_event(
        cls,
        event_id: str,
        block_id: str,
        task_id: str,
        ctrl_id: str,
        event_kind: str,
        lifecycle_state: str,
        observed_at_ms: int,
        *,
        milestone_id: str | None = None,
        parent_event_id: str | None = None,
        admitted: int = 0,
        flags: list[str] | None = None,
        eta: tuple[int, int, int] | None = None,
        eta_basis: list[str] | None = None,
        milestone_acceptance: bool = False,
        routing: dict[str, object] | None = None,
    ) -> dict[str, object]:
        event = cls._notification_event(
            event_id, block_id, event_kind, lifecycle_state, observed_at_ms,
            parent_event_id=parent_event_id, admitted_proof_weight=admitted,
            proof_receipt_ids=[f"proof-{event_id}"] if admitted else [],
            proof_required_classes=["MILESTONE_ACCEPTANCE"] if milestone_acceptance else ["SOURCE"],
            flags=flags, milestone_id=milestone_id or block_id, committed_weight=1,
        )
        event.update(ctrl_id=ctrl_id, task_id=task_id, owner_id=f"owner-{task_id}")
        event["material_update_sentence"] = f"Accepted signal for {task_id}."
        if eta is not None:
            event["eta"] = {
                "start_ms": eta[0], "end_ms": eta[1], "confidence": eta[2],
                "basis_receipt_ids": list(eta_basis or [f"eta-{event_id}"]),
            }
        if routing is not None:
            event["schema_version"] = 2
            event["measurement"] = {
                "state": "UNMEASURED", "committed_weight": None,
                "admitted_proof_weight": 0, "basis_receipt_ids": [],
            }
            event["proof"] = {"required_classes": [], "receipt_ids": [], "claim_limit": "Routing evidence only."}
            event["material_update_sentence"] = None
            event["topology"] = {
                "node_kind": "BLOCK", "input_receipt_ids": [],
                "dispatch_receipt_id": None, "completion_receipt_id": None,
                "cost_receipt_ids": [], "release_receipt_ids": [],
                "routing_evidence": routing,
            }
        return event

    def test_independent_project_progress_is_read_only_and_unmeasured(self) -> None:
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DELETE FROM thread_spawn_edges")
            connection.commit()
        app = console.App(self.codex_home, self.config)
        host_before = self.database.read_bytes()
        result = app.measurable_progress("project:alpha")
        self.assertEqual(result["status"], "UNMEASURED")
        self.assertIsNone(result["percent"])
        self.assertEqual(result["scope_binding"]["ctrl_ids"], [])
        self.assertEqual(result["progress_queue"]["status"], "CURRENT")
        self.assertTrue(all(not segment["rows"] for segment in result["progress_queue"]["segments"]))
        self.assertEqual(self.database.read_bytes(), host_before)
        self.assertFalse(console._is_authoritative_ctrl_for_execution({"controller_classification": "unavailable"}))
        self.assertEqual(app.measurable_progress("foreign-project")["status"], "UNKNOWN")

        event = self._progress_queue_event(
            "independent-start", "independent-block", "task", "retained-owner", "BLOCK_CREATED", "ACTIVE", 10,
        )
        app.progress_ledger.append(event)
        result = app.measurable_progress("project:alpha")
        self.assertEqual(result["progress_queue"]["status"], "CURRENT")
        self.assertEqual(result["scope_binding"]["ctrl_ids"], ["retained-owner"])
        self.assertEqual(result["progress_queue"]["segments"][0]["rows"][0]["task_id"], "task")
        self.assertEqual(self.database.read_bytes(), host_before)
        self.assertEqual(console.App(self.codex_home, self.config).measurable_progress("project:alpha"), result)

    def test_independent_project_progress_rejects_foreign_and_mixed_bindings(self) -> None:
        for foreign in (False, True):
            with self.subTest(foreign=foreign):
                ledger = console.ProgressLedger(self.root / f"read-scope-{foreign}.jsonl")
                first = self._progress_queue_event("read-a", "read-a", "task", "owner-a", "BLOCK_CREATED", "ACTIVE", 10)
                if foreign:
                    first["project_id"] = "project:foreign"
                ledger.append(first)
                if not foreign:
                    ledger.append(self._progress_queue_event("read-b", "read-b", "task", "owner-b", "BLOCK_CREATED", "ACTIVE", 20))
                result = ledger.project_progress_queue_bundle("project:alpha", {}, project_tasks={"task": {"task_name": "Task"}})
                self.assertEqual(result["status"], "UNKNOWN")
                self.assertEqual(result["progress_queue"]["reason"], "MIXED_SCOPE_REJECTED")
                self.assertIsNone(result["percent"])

    def test_project_progress_queue_is_atomic_ctrl_first_and_receipt_bound(self) -> None:
        self._confirm_root_ctrl()
        self._add_same_project_ctrl()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "UPDATE thread_spawn_edges SET status='open' WHERE child_thread_id='review'"
            )
            connection.commit()
        app = console.App(self.codex_home, self.config)

        def route(task_id: str, route_id: str) -> dict[str, object]:
            return {
                "disposition": "KEEP_ROLE", "route": route_id,
                "selected_owner": f"owner-{task_id}", "selected_task_id": task_id,
                "project_active": True, "release_event": None,
                "scope": {
                    "goal_id": "goal", "request_id": f"request-{task_id}", "task_id": task_id,
                    "mutable_surface": f"surface:{task_id}", "owner_id": f"owner-{task_id}",
                },
                "critical_path": False, "recovery": None,
            }

        def blocked_route(release_event: str, *, condition: str, authority: str) -> dict[str, object]:
            return {
                "disposition": "KEEP_ROLE", "route": "hard_blocked", "selected_owner": "owner-lead",
                "selected_task_id": "lead", "project_active": False, "release_event": release_event,
                "scope": {"goal_id": "goal", "request_id": "request", "task_id": "lead", "mutable_surface": "surface:lead", "owner_id": "owner-lead"},
                "critical_path": False,
                "recovery": {
                    "state": "CONTROL_PATH_FAILURE", "action": "request_authority", "attempts": 3,
                    "permitted_route_ids": ["route-a"], "failed_route_id": "route-a",
                    "evidence_receipt_ids": ["lead-start"], "release_condition": condition,
                    "responsible_authority": authority, "smallest_solution": "Release the exact lane.",
                },
            }

        events = [
            self._progress_queue_event("m1-start", "m1", "task", "root", "BLOCK_CREATED", "ACTIVE", 10, milestone_acceptance=True),
            self._progress_queue_event("m1-review", "m1", "task", "root", "STATE_CHANGED", "REVIEW", 20, parent_event_id="m1-start", milestone_acceptance=True),
            self._progress_queue_event("m1-verified", "m1", "task", "root", "PROOF_ADMITTED", "VERIFIED", 21, parent_event_id="m1-review", admitted=1, milestone_acceptance=True),
            self._progress_queue_event("m1-done", "m1", "task", "root", "ACCEPTED", "ACCEPTED", 22, parent_event_id="m1-verified", admitted=1, milestone_acceptance=True),
            self._progress_queue_event("m2-start", "m2", "task", "root", "BLOCK_CREATED", "ACTIVE", 30, eta=(40, 80, 75), eta_basis=["m1-done"], milestone_acceptance=True),
            self._progress_queue_event("ready-start", "ready", "review", "root", "BLOCK_CREATED", "READY", 39),
            self._progress_queue_event("ready-route", "ready", "review", "root", "STATE_CHANGED", "READY", 40, parent_event_id="ready-start", routing=route("review", "normal_task")),
            self._progress_queue_event("lead-start", "lead-block", "lead", "root", "BLOCK_CREATED", "ACTIVE", 50),
            self._progress_queue_event(
                "lead-release", "lead-block", "lead", "root", "STATE_CHANGED", "WAITING_EXTERNAL", 60,
                parent_event_id="lead-start", flags=["blocked", "waiting_external"],
                routing=blocked_route("lead-release", condition="Owner releases the lane.", authority="owner-lead"),
            ),
            self._progress_queue_event(
                "lead-blocked", "lead-block", "lead", "root", "STATE_CHANGED", "ACTIVE", 61,
                parent_event_id="lead-release", flags=["blocked", "waiting_external"],
                routing=blocked_route("lead-release", condition="Wrong latest event must not replace release truth.", authority="wrong-owner"),
            ),
            self._progress_queue_event("other-active", "other-m1", "other-task", "other-ctrl", "BLOCK_CREATED", "ACTIVE", 70),
        ]
        for event in events:
            with self.subTest(event_id=event["event_id"]):
                self.assertEqual(app.progress_ledger.append(event)["status"], "appended")
        self.assertEqual(app.progress_ledger.append(events[-1])["status"], "unchanged")

        result = app.measurable_progress("project:alpha")
        projection = result["progress_queue"]
        self.assertEqual(projection["status"], "CURRENT", projection)
        self.assertEqual(projection["accepted_cursor"], result["cursor"])
        self.assertEqual(projection["scope_binding"], {
            "project_id": "project:alpha", "ctrl_ids": ["other-ctrl", "root"], "cursor": result["cursor"],
        })
        active, queue = projection["segments"]
        self.assertEqual(active["segment_id"], "segment.project.progress.active")
        self.assertEqual(queue["segment_id"], "segment.project.progress.queue")
        self.assertEqual([row["task_id"] for row in active["rows"]], ["other-task", "task"])
        task = next(row for row in active["rows"] if row["task_id"] == "task")
        self.assertEqual(task["scope_binding"]["ctrl_id"], "root")
        self.assertEqual(task["progress"], {
            "state": "KNOWN", "completed_milestones": 1, "total_milestones": 2, "percent": 50.0,
        })
        self.assertEqual(task["eta"]["state"], "KNOWN")
        self.assertEqual(task["eta"]["basis_receipt_ids"], ["m1-done"])
        self.assertEqual(task["eta"]["basis_receipts"][0]["event_digest"], app.progress_ledger.replay()["events"]["m1-done"])
        self.assertEqual(task["freshness"], {"state": "CURRENT", "observed_at_ms": 30})
        self.assertIn("review", [row["task_id"] for row in queue["rows"]], {"projection": projection, "blocks": result["blocks"]})
        ready = next(row for row in queue["rows"] if row["task_id"] == "review")
        blocked = next(row for row in queue["rows"] if row["task_id"] == "lead")
        self.assertEqual((ready["queue_state"], ready["runnable"]), ("QUEUED_NOT_STARTED", True))
        self.assertEqual((blocked["queue_state"], blocked["runnable"]), ("SCOPED_BLOCKED", False))
        self.assertEqual(blocked["blocked_recovery"]["blocked_release_condition"]["condition"], "Owner releases the lane.")
        self.assertEqual(blocked["blocked_recovery"]["blocked_suggested_recovery"]["responsible_authority"], "owner-lead")
        self.assertFalse(blocked["blocked_recovery"]["blocked_critical_path"])
        self.assertEqual({row["scope_binding"]["ctrl_id"] for row in active["rows"]}, {"root", "other-ctrl"})
        self.assertEqual(len([row for row in active["rows"] if row["task_id"] == "other-task"]), 1)

        restarted = console.App(self.codex_home, self.config)
        self.assertEqual(restarted.measurable_progress("project:alpha")["progress_queue"], projection)

    def test_project_progress_queue_rejects_cross_ctrl_and_clears_stale_live_values(self) -> None:
        self._confirm_root_ctrl()
        self._add_same_project_ctrl()
        app = console.App(self.codex_home, self.config)
        app.progress_ledger.append(self._progress_queue_event(
            "cross-scope", "cross", "other-task", "root", "BLOCK_CREATED", "ACTIVE", 10,
            eta=(20, 30, 80), milestone_acceptance=True,
        ))
        rejected_bundle = app.measurable_progress("project:alpha")
        rejected = rejected_bundle["progress_queue"]
        self.assertEqual((rejected["status"], rejected["reason"], rejected["segments"][0]["rows"]), ("RESYNC_REQUIRED", "MIXED_SCOPE_REJECTED", []))
        self.assertEqual((rejected_bundle["status"], rejected_bundle["percent"], rejected_bundle["blocks"]), ("UNKNOWN", None, []))
        self.assertEqual(rejected["scope_binding"]["ctrl_ids"], ["other-ctrl", "root"])

        isolated_home = self.root / "stale-codex"
        isolated_home.mkdir()
        isolated_home.joinpath("state_5.sqlite").write_bytes(self.database.read_bytes())
        stale_app = console.App(isolated_home, self.config, self.root / "console" / "stale.sqlite3")
        stale_app.progress_ledger.append(self._progress_queue_event(
            "stale-start", "stale-milestone", "task", "root", "BLOCK_CREATED", "ACTIVE", 10,
            eta=(20, 30, 80), milestone_acceptance=True,
        ))
        stale_app.progress_ledger.append(self._progress_queue_event(
            "stale-mark", "stale-milestone", "task", "root", "STATE_CHANGED", "ACTIVE", 20,
            parent_event_id="stale-start", flags=["stale"], eta=(20, 30, 80), milestone_acceptance=True,
        ))
        stale_result = stale_app.measurable_progress("project:alpha")
        self.assertEqual((stale_result["status"], stale_result["percent"], stale_result["blocks"]), ("UNKNOWN", None, []))
        self.assertEqual(
            (stale_result["progress_queue"]["status"], stale_result["progress_queue"]["reason"], stale_result["progress_queue"]["available"]),
            ("RESYNC_REQUIRED", "STALE_SOURCE", False),
        )
        restarted_stale = console.App(isolated_home, self.config, self.root / "console" / "stale-restart.sqlite3")
        self.assertEqual(restarted_stale.measurable_progress("project:alpha"), stale_result)

    def test_project_progress_queue_gap_requires_snapshot_resync(self) -> None:
        self._confirm_root_ctrl()
        app = console.App(self.codex_home, self.config)
        app.progress_ledger.append(self._progress_queue_event(
            "gap-source", "gap-block", "task", "root", "BLOCK_CREATED", "ACTIVE", 10,
        ))
        retained_bytes = app.progress_ledger._state.path.read_bytes()
        record = json.loads(retained_bytes.decode("utf-8"))
        record["event_seq"] = 2
        app.progress_ledger._state.path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        result = app.measurable_progress("project:alpha")
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual((result["percent"], result["blocks"]), (None, []))
        self.assertEqual((result["progress_queue"]["status"], result["progress_queue"]["reason"]), ("RESYNC_REQUIRED", "RESYNC_REQUIRED"))
        app.progress_ledger._state.path.write_bytes(retained_bytes)
        restarted = console.App(self.codex_home, self.config)
        restored = restarted.measurable_progress("project:alpha")
        self.assertNotEqual(restored["status"], "UNKNOWN")
        self.assertEqual(restored["progress_queue"]["status"], "CURRENT")

    def test_project_progress_queue_distinguishes_typed_non_runnable_states(self) -> None:
        self._confirm_root_ctrl()
        now = 2_000_000_200_000
        task_ids = ["dependency-task", "capacity-task", "review-task", "failed-task", "unknown-task", "ready-task"]
        with closing(sqlite3.connect(self.database)) as connection:
            for task_id in task_ids:
                connection.execute(
                    "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (task_id, task_id.replace("-", " ").title(), "C:/work/alpha", now // 1000, now // 1000,
                     now, now, "gpt-5.6-luna", "medium", 1, 0, "", "main", "", "", "", 0),
                )
                connection.execute("INSERT INTO thread_spawn_edges VALUES (?,?,?)", ("root", task_id, "open"))
            connection.commit()
        app = console.App(self.codex_home, self.config)

        def waiting_route(state: str, task_id: str) -> dict[str, object]:
            return {
                "disposition": "KEEP_ROLE", "route": "waiting", "selected_owner": f"owner-{task_id}",
                "selected_task_id": task_id, "project_active": True, "release_event": f"release-{task_id}",
                "scope": {"goal_id": "goal", "request_id": f"request-{task_id}", "task_id": task_id, "mutable_surface": f"surface:{task_id}", "owner_id": f"owner-{task_id}"},
                "critical_path": False,
                "recovery": {
                    "state": state, "action": "wait_for_release", "attempts": 1,
                    "permitted_route_ids": ["route-a"], "failed_route_id": "route-a",
                    "evidence_receipt_ids": [], "release_condition": f"Release {task_id}.",
                    "responsible_authority": f"owner-{task_id}", "smallest_solution": "Wait for the retained release.",
                },
            }

        events = [
            self._progress_queue_event("capacity-start", "capacity-block", "capacity-task", "root", "BLOCK_CREATED", "ACTIVE", 10),
            self._progress_queue_event("capacity-wait", "capacity-block", "capacity-task", "root", "WAIT_CHANGED", "WAITING_EXTERNAL", 20, parent_event_id="capacity-start", routing=waiting_route("WAITING_FOR_CAPACITY", "capacity-task")),
            self._progress_queue_event("dependency", "dependency-block", "dependency-task", "root", "BLOCK_CREATED", "WAITING_DEPENDENCY", 30),
            self._progress_queue_event("review-gate", "review-block", "review-task", "root", "BLOCK_CREATED", "REVIEW", 40),
            self._progress_queue_event("failed-start", "failed-block", "failed-task", "root", "BLOCK_CREATED", "ACTIVE", 50),
            self._progress_queue_event("failed-wait", "failed-block", "failed-task", "root", "WAIT_CHANGED", "WAITING_EXTERNAL", 60, parent_event_id="failed-start", routing=waiting_route("CONTROL_PATH_FAILURE", "failed-task")),
            self._progress_queue_event("unknown", "unknown-block", "unknown-task", "root", "BLOCK_CREATED", "PLANNED", 70),
            self._progress_queue_event("ready-no-route", "ready-no-route", "ready-task", "root", "BLOCK_CREATED", "READY", 80),
        ]
        events[2]["dependency_ids"] = ["capacity-block"]
        for event in events:
            app.progress_ledger.append(event)
        rows = app.measurable_progress("project:alpha")["progress_queue"]["segments"][1]["rows"]
        states = {row["task_id"]: (row["queue_state"], row["runnable"]) for row in rows}
        self.assertEqual(states, {
            "capacity-task": ("WAITING_FOR_CAPACITY", False),
            "dependency-task": ("WAITING_FOR_DEPENDENCY", False),
            "failed-task": ("FAILED", False),
            "review-task": ("REVIEW_GATED", False),
            "unknown-task": ("UNKNOWN", False),
            "ready-task": ("UNKNOWN", False),
        })

    def test_project_progress_queue_direct_lifecycle_classification_is_fail_closed(self) -> None:
        classify = console.ProgressLedger.classify_progress_queue_state
        common = {
            "stale": False, "routing": None, "flags": set(), "task_id": "task",
            "owner_id": "owner", "has_dependencies": False, "has_blocked_recovery": False,
        }
        self.assertEqual(classify("REVIEW_PENDING", **common), ("REVIEW_GATED", False))
        self.assertEqual(classify("BLOCKED", **common), ("UNKNOWN", False))
        self.assertEqual(classify("FAILED", **common), ("FAILED", False))
        self.assertEqual(classify("READY", **common), ("UNKNOWN", False))
        hard_blocked = {**common, "routing": {"route": "hard_blocked"}}
        self.assertEqual(classify("ACTIVE", **hard_blocked), ("UNKNOWN", False))
        self.assertEqual(classify("ACTIVE", **{**hard_blocked, "has_blocked_recovery": True}), ("SCOPED_BLOCKED", False))

    def test_project_progress_queue_rejects_event_identity_conflict_across_ctrls(self) -> None:
        self._confirm_root_ctrl()
        self._add_same_project_ctrl()
        app = console.App(self.codex_home, self.config)

        def route(task_id: str) -> dict[str, object]:
            return {
                "disposition": "KEEP_ROLE", "route": "normal_task",
                "selected_owner": f"owner-{task_id}", "selected_task_id": task_id,
                "project_active": True, "release_event": None,
                "scope": {
                    "goal_id": "goal", "request_id": f"request-{task_id}", "task_id": task_id,
                    "mutable_surface": f"surface:{task_id}", "owner_id": f"owner-{task_id}",
                },
                "critical_path": False, "recovery": None,
            }

        app.progress_ledger.append(self._progress_queue_event(
            "root-start", "root-block", "task", "root", "BLOCK_CREATED", "ACTIVE", 10,
        ))
        app.progress_ledger.append(self._progress_queue_event(
            "other-start", "other-block", "other-task", "other-ctrl", "BLOCK_CREATED", "ACTIVE", 11,
        ))
        app.progress_ledger.append(self._progress_queue_event(
            "shared-route", "root-block", "task", "root", "STATE_CHANGED", "ACTIVE", 20,
            parent_event_id="root-start", routing=route("task"),
        ))
        self.assertEqual(app.progress_ledger.append(self._progress_queue_event(
            "shared-route", "other-block", "other-task", "other-ctrl", "STATE_CHANGED", "ACTIVE", 21,
            parent_event_id="other-start", routing=route("other-task"),
        ))["status"], "conflicted")

        rejected = app.measurable_progress("project:alpha")
        self.assertEqual((rejected["status"], rejected["percent"], rejected["blocks"]), ("UNKNOWN", None, []))
        self.assertEqual(
            (rejected["progress_queue"]["status"], rejected["progress_queue"]["reason"]),
            ("RESYNC_REQUIRED", "SOURCE_DIGEST_CONFLICT"),
        )
        restarted = console.App(self.codex_home, self.config, self.root / "console" / "conflict-restart.sqlite3")
        self.assertEqual(restarted.measurable_progress("project:alpha"), rejected)

    def test_project_progress_queue_rejects_aggregate_topology_unknowns(self) -> None:
        self._confirm_root_ctrl()
        app = console.App(self.codex_home, self.config)

        def route() -> dict[str, object]:
            return {
                "disposition": "KEEP_ROLE", "route": "normal_task",
                "selected_owner": "owner-task", "selected_task_id": "task",
                "project_active": True, "release_event": None,
                "scope": {
                    "goal_id": "goal", "request_id": "request-task", "task_id": "task",
                    "mutable_surface": "surface:task", "owner_id": "owner-task",
                },
                "critical_path": False, "recovery": None,
            }

        app.progress_ledger.append(self._progress_queue_event(
            "aggregate-start", "aggregate-block", "task", "root", "BLOCK_CREATED", "ACTIVE", 10,
        ))
        app.progress_ledger.append(self._progress_queue_event(
            "aggregate-gap", "aggregate-block", "task", "root", "STATE_CHANGED", "ACTIVE", 20,
            parent_event_id="missing-parent-event", routing=route(),
        ))
        app.progress_ledger.append(self._progress_queue_event(
            "aggregate-latest", "aggregate-block", "task", "root", "STATE_CHANGED", "ACTIVE", 30,
            parent_event_id="aggregate-gap", routing=route(),
        ))

        rejected = app.measurable_progress("project:alpha")
        self.assertEqual((rejected["status"], rejected["percent"], rejected["blocks"]), ("UNKNOWN", None, []))
        self.assertEqual(
            (rejected["progress_queue"]["status"], rejected["progress_queue"]["reason"]),
            ("RESYNC_REQUIRED", "TOPOLOGY_SCOPE_CONFLICT"),
        )
        restarted = console.App(self.codex_home, self.config, self.root / "console" / "aggregate-restart.sqlite3")
        self.assertEqual(restarted.measurable_progress("project:alpha"), rejected)

    def test_project_progress_queue_conflict_cursor_and_eta_fail_atomically(self) -> None:
        self._confirm_root_ctrl()
        app = console.App(self.codex_home, self.config)
        app.progress_ledger.append(self._progress_queue_event(
            "eta-source", "eta-block", "task", "root", "BLOCK_CREATED", "ACTIVE", 10,
            eta=(20, 30, 80), eta_basis=["not-a-retained-receipt"],
        ))
        current = app.measurable_progress("project:alpha")
        row = current["progress_queue"]["segments"][0]["rows"][0]
        self.assertEqual((row["eta"]["state"], row["freshness"]["state"]), ("UNKNOWN", "CURRENT"))

        topology = self._progress_queue_event(
            "routing-conflict", "eta-block", "task", "root", "STATE_CHANGED", "ACTIVE", 20,
            parent_event_id="eta-source", routing={
                "disposition": "KEEP_ROLE", "route": "normal_task", "selected_owner": "owner-task",
                "selected_task_id": "task", "project_active": True, "release_event": None,
                "scope": {"goal_id": "goal", "request_id": "request", "task_id": "task", "mutable_surface": "surface:task", "owner_id": "owner-task"},
                "critical_path": False, "recovery": None,
            },
        )
        app.progress_ledger.append(topology)
        app.progress_ledger.append({**topology, "source": "swarm_execution_adapter"})
        conflicted = app.measurable_progress("project:alpha")
        self.assertEqual((conflicted["status"], conflicted["progress_queue"]["reason"]), ("UNKNOWN", "TOPOLOGY_SCOPE_CONFLICT"))
        self.assertEqual((conflicted["percent"], conflicted["blocks"]), (None, []))

        isolated_home = self.root / "cursor-codex"
        isolated_home.mkdir()
        isolated_home.joinpath("state_5.sqlite").write_bytes(self.database.read_bytes())
        cursor_app = console.App(isolated_home, self.config, self.root / "console" / "cursor.sqlite3")
        cursor_app.progress_ledger.append(self._progress_queue_event(
            "cursor-source", "cursor-block", "task", "root", "BLOCK_CREATED", "ACTIVE", 10,
        ))
        original = cursor_app.progress_ledger._project_topology_from_records

        def stale_topology(*args: object, **kwargs: object) -> dict[str, object]:
            projected = original(*args, **kwargs)
            projected["through_cursor"] = int(projected["through_cursor"]) - 1
            return projected

        with mock.patch.object(cursor_app.progress_ledger, "_project_topology_from_records", side_effect=stale_topology):
            changed = cursor_app.measurable_progress("project:alpha")
        self.assertEqual((changed["status"], changed["progress_queue"]["reason"]), ("UNKNOWN", "TOPOLOGY_SCOPE_CONFLICT"))

    def test_notification_feed_is_pure_filtered_and_ledger_bound(self) -> None:
        self._confirm_root_ctrl()
        app = console.App(self.codex_home, self.config)
        self._append_notification_fixture(app)
        with closing(sqlite3.connect(app.store.path)) as connection:
            before = connection.execute("SELECT COUNT(*) FROM store_metadata").fetchone()[0]
        with mock.patch.object(app.auto_bridge, "run", side_effect=AssertionError("read must not invoke a model")), \
             mock.patch.object(app.auto_bridge, "reconcile", side_effect=AssertionError("read must not invoke a model")):
            first = app.notification_feed("root", "project:alpha")
            second = app.notification_feed("root", "project:alpha")
        self.assertEqual(first, second)
        self.assertEqual(
            [item["kind"] for item in first["unread"]],
            ["MILESTONE_COMPLETED", "REVIEW_COMPLETED", "REVIEW_REQUESTED", "BLOCKER"],
        )
        self.assertNotIn("ordinary-progress", {item["source_event_id"] for item in first["unread"]})
        self.assertNotIn("generic-source-proof", {item["source_event_id"] for item in first["unread"]})
        self.assertNotIn("accepted-block", {item["source_event_id"] for item in first["unread"]})
        self.assertEqual(
            next(item for item in first["unread"] if item["kind"] == "REVIEW_COMPLETED")["sentence"],
            "An independent-review receipt has been admitted.",
        )
        self.assertTrue(all(item["source_event_digest"] in item["evidence_refs"] for item in first["unread"]))
        self.assertTrue(all(item["action_target"]["project_id"] == "project:alpha" for item in first["unread"]))
        self.assertEqual(first["recent_seen"], [])
        with closing(sqlite3.connect(app.store.path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM store_metadata").fetchone()[0], before)
        self.assertEqual(
            app.progress_ledger.append(self._notification_event(
                "ordinary-progress", "ordinary-block", "BLOCK_CREATED", "ACTIVE", 30,
            ))["status"],
            "unchanged",
        )
        self.assertEqual(app.notification_feed("root", "project:alpha"), first)

    def test_notification_seen_receipt_is_idempotent_restart_safe_and_revision_specific(self) -> None:
        self._confirm_root_ctrl()
        state_path = self.root / "console" / "notifications.sqlite3"
        app = console.App(self.codex_home, self.config, state_path)
        self._append_notification_fixture(app)
        original = app.notification_feed("root", "project:alpha")
        seen_id = next(
            item["id"] for item in original["unread"] if item["source_event_id"] == "blocker-created"
        )
        payload = {"ctrl_id": "root", "project_id": "project:alpha", "notification_ids": [seen_id]}
        with mock.patch.object(console.time, "time", return_value=1):
            first = app.mark_notifications_seen(payload)
            replay = app.mark_notifications_seen(payload)
        self.assertEqual((first["newly_seen"], replay["newly_seen"]), (1, 0))
        self.assertNotIn(seen_id, {item["id"] for item in replay["feed"]["unread"]})
        self.assertEqual([item["id"] for item in replay["feed"]["recent_seen"]], [seen_id])
        with closing(sqlite3.connect(state_path)) as connection:
            retained_state = json.loads(connection.execute(
                "SELECT value FROM store_metadata WHERE key LIKE 'notification_seen_v1:%'",
            ).fetchone()[0])
        self.assertEqual(
            set(retained_state["receipts"][0]),
            {"notification_id", "scope_digest", "source_event_id", "source_event_digest", "seen_at_ms"},
        )
        self.assertNotIn("item", retained_state["receipts"][0])

        restarted = console.App(self.codex_home, self.config, state_path)
        retained = restarted.notification_feed("root", "project:alpha")
        self.assertNotIn(seen_id, {item["id"] for item in retained["unread"]})
        self.assertEqual([item["id"] for item in retained["recent_seen"]], [seen_id])

        restarted.progress_ledger.append(self._notification_event(
            "blocker-revised", "blocked-block", "WAIT_CHANGED", "WAITING_EXTERNAL", 40,
            parent_event_id="blocker-created", flags=["blocked", "waiting_external"],
        ))
        updated = restarted.notification_feed("root", "project:alpha")
        self.assertEqual(updated["unread"][0]["source_event_id"], "blocker-revised")
        self.assertEqual(updated["unread"][0]["subject_id"], "blocked-block")
        self.assertNotEqual(updated["unread"][0]["id"], seen_id)

        (self.codex_home / "swarm" / "progress-ledger.jsonl").unlink()
        restarted.progress_ledger.projection_path.unlink(missing_ok=True)
        evicted_app = console.App(self.codex_home, self.config, state_path)
        evicted = evicted_app.notification_feed("root", "project:alpha")
        self.assertEqual((evicted["unread"], evicted["recent_seen"]), ([], []))
        self.assertEqual(evicted_app.progress_ledger.append(self._notification_event(
            "fresh-blocker", "fresh-block", "BLOCK_CREATED", "WAITING_EXTERNAL", 2000,
            flags=["blocked", "waiting_external"],
        ))["status"], "appended")
        fresh = evicted_app.notification_feed("root", "project:alpha")["unread"][0]
        with mock.patch.object(console.time, "time", return_value=2):
            pruned = evicted_app.mark_notifications_seen({
                "ctrl_id": "root", "project_id": "project:alpha", "notification_ids": [fresh["id"]],
            })
        self.assertEqual(pruned["pruned"], 1)
        with closing(sqlite3.connect(state_path)) as connection:
            retained_state = json.loads(connection.execute(
                "SELECT value FROM store_metadata WHERE key LIKE 'notification_seen_v1:%'",
            ).fetchone()[0])
        self.assertEqual([receipt["notification_id"] for receipt in retained_state["receipts"]], [fresh["id"]])

    def test_notification_seen_retention_tracks_all_current_ledger_identities(self) -> None:
        self._confirm_root_ctrl()
        state_path = self.root / "console" / "notification-retention.sqlite3"
        app = console.App(self.codex_home, self.config, state_path)
        records = []
        for index in range(1025):
            event = validate_progress_material_event(self._compact_blocker_event(index))
            record = app.progress_ledger._record(event, index + 1)
            records.append(json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n")
        with app.progress_ledger._state.locked():
            app.progress_ledger._state.replace_bytes_unlocked(b"".join(records))
        observed_scope = ({}, [{"id": "t"}], {"t"}, {})
        with mock.patch.object(app, "_observed_scope", return_value=observed_scope):
            items, truncated = app._notification_items("c", "p")
        self.assertFalse(truncated)
        self.assertEqual(len(items), 1025)
        current = {item["id"]: item for item in items}
        oldest = min(items, key=lambda item: item["material_sequence"])["id"]
        result = app.store.mark_notifications_seen(
            principal_id=app._notification_principal(), ctrl_id="c", project_id="p",
            items=current, notification_ids=list(current), now_ms=1,
        )
        self.assertEqual((result["newly_seen"], result["pruned"]), (1025, 0))

        restarted = console.App(self.codex_home, self.config, state_path)
        with mock.patch.object(restarted, "_observed_scope", return_value=observed_scope):
            retained_items, retained_truncated = restarted._notification_items("c", "p")
        retained_current = {item["id"]: item for item in retained_items}
        retained_seen = restarted.store.notification_seen(
            principal_id=restarted._notification_principal(), ctrl_id="c", project_id="p",
            items=retained_current,
        )
        self.assertFalse(retained_truncated)
        self.assertEqual(len(retained_seen), 1025)
        self.assertIn(oldest, {receipt["notification_id"] for receipt in retained_seen})
        with mock.patch.object(restarted, "_observed_scope", return_value=observed_scope):
            self.assertEqual(restarted.notification_feed("c", "p")["unread"], [])

    def test_notification_ack_rejects_unknown_cross_scope_and_corrupt_state_without_mutation(self) -> None:
        self._confirm_root_ctrl()
        state_path = self.root / "console" / "notification-guards.sqlite3"
        app = console.App(self.codex_home, self.config, state_path)
        self._append_notification_fixture(app)
        known = app.notification_feed("root", "project:alpha")["unread"][0]["id"]
        with self.assertRaisesRegex(console.ConsoleError, "1-64 unique"):
            app.mark_notifications_seen({"ctrl_id": "root", "project_id": "project:alpha", "notification_ids": []})
        with self.assertRaisesRegex(console.ConsoleError, "not current"):
            app.mark_notifications_seen({"ctrl_id": "root", "project_id": "project:alpha", "notification_ids": ["0" * 64]})
        with self.assertRaisesRegex(console.ConsoleError, "observed project|does not belong"):
            app.mark_notifications_seen({"ctrl_id": "root", "project_id": "project:other", "notification_ids": [known]})
        with closing(sqlite3.connect(state_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM store_metadata").fetchone()[0], 0)
            key = app.store._notification_seen_key(app._notification_principal(), "root", "project:alpha")
            connection.execute("INSERT INTO store_metadata(key, value) VALUES (?, ?)", (key, "{invalid"))
            connection.commit()
            before = connection.execute("SELECT value FROM store_metadata WHERE key = ?", (key,)).fetchone()[0]
        with self.assertRaisesRegex(console.ConsoleError, "notification seen state is invalid"):
            app.mark_notifications_seen({"ctrl_id": "root", "project_id": "project:alpha", "notification_ids": [known]})
        with closing(sqlite3.connect(state_path)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM store_metadata WHERE key = ?", (key,)).fetchone()[0], before)

    def test_notification_routes_require_exact_local_authorization_and_do_not_execute_actions(self) -> None:
        self._confirm_root_ctrl()
        app = console.App(self.codex_home, self.config)
        app.notification_feed = mock.Mock(return_value={"ok": True, "unread": [], "recent_seen": []})
        app.mark_notifications_seen = mock.Mock(return_value={"ok": True})

        rejected = self._handler("127.0.0.1", "127.0.0.1:4788", origin="http://evil.example", token=app.token)
        rejected.server = SimpleNamespace(app=app)
        rejected.path = "/api/notifications?ctrl_id=root&project_id=project%3Aalpha"
        rejected._error = mock.Mock()
        rejected._json = mock.Mock()
        rejected.do_GET()
        rejected._error.assert_called_once_with(
            console.HTTPStatus.FORBIDDEN, "notification feed requires local same-origin authorization",
        )
        app.notification_feed.assert_not_called()

        allowed = self._handler(
            "127.0.0.1", "127.0.0.1:4788", origin="http://127.0.0.1:4788", token=app.token,
        )
        allowed.server = SimpleNamespace(app=app)
        allowed.path = "/api/notifications?ctrl_id=root&project_id=project%3Aalpha"
        allowed._json = mock.Mock()
        allowed.do_GET()
        app.notification_feed.assert_called_once_with("root", "project:alpha")

        write_rejected = self._handler(
            "127.0.0.1", "127.0.0.1:4788", origin="http://127.0.0.1:4788", token="wrong",
        )
        write_rejected.server = SimpleNamespace(app=app)
        write_rejected.path = "/api/notifications/seen"
        write_rejected._error = mock.Mock()
        write_rejected._payload = mock.Mock(side_effect=AssertionError("auth must precede payload parsing"))
        write_rejected.do_POST()
        write_rejected._error.assert_called_once_with(console.HTTPStatus.FORBIDDEN, "invalid console write token")
        app.mark_notifications_seen.assert_not_called()

    def test_run_log_is_ctrl_first_agent_filtered_private_and_pure(self) -> None:
        self._confirm_root_ctrl()
        self._add_same_project_ctrl()
        app = console.App(self.codex_home, self.config)
        root_event = self._notification_event(
            "run-root", "run-root-block", "BLOCK_CREATED", "ACTIVE", 10,
        )
        root_event["material_update_sentence"] = "PRIVATE_PROMPT_7a secret-token-7a stdout-marker-7a"
        other_event = self._notification_event(
            "run-other", "run-other-block", "BLOCK_CREATED", "ACTIVE", 11,
        )
        other_event.update(ctrl_id="other-ctrl", task_id="other-task", owner_id="other-owner")
        spoofed_event = self._notification_event(
            "run-spoofed", "run-spoofed-block", "BLOCK_CREATED", "ACTIVE", 12,
        )
        spoofed_event.update(task_id="other-task", owner_id="other-owner")
        self.assertEqual(app.progress_ledger.append(root_event)["status"], "appended")
        self.assertEqual(app.progress_ledger.append(other_event)["status"], "appended")
        self.assertEqual(app.progress_ledger.append(spoofed_event)["status"], "appended")
        ledger_before = app.progress_ledger._state.path.read_bytes()
        with closing(sqlite3.connect(app.store.path)) as connection:
            store_before = connection.execute("SELECT COUNT(*) FROM store_metadata").fetchone()[0]
        with mock.patch.object(app.auto_bridge, "run", side_effect=AssertionError("read must not invoke a model")), \
             mock.patch.object(app.auto_bridge, "reconcile", side_effect=AssertionError("read must not invoke a model")):
            first = app.run_log("root")
            replay = app.run_log("root", project_id="project:alpha")
            task_view = app.run_log("root", project_id="project:alpha", agent_id="task")
            owner_view = app.run_log("root", project_id="project:alpha", agent_id="owner-task")
            unknown = app.run_log("root", project_id="project:alpha", agent_id="unknown-agent")
        self.assertEqual(first, replay)
        self.assertEqual([item["event_id"] for item in first["items"]], ["run-root"])
        self.assertNotIn("other-owner", json.dumps(first))
        self.assertEqual(task_view["items"], owner_view["items"])
        self.assertEqual(unknown["items"], [])
        item = first["items"][0]
        self.assertEqual(
            (item["project_id"], item["ctrl_id"], item["agent_id"], item["summary"]),
            ("project:alpha", "root", "task", "Work was added."),
        )
        serialized = json.dumps(first)
        for private in ("PRIVATE_PROMPT_7a", "secret-token-7a", "stdout-marker-7a", "provenance", "claim_limit\": \"Source"):
            self.assertNotIn(private, serialized)
        self.assertEqual(app.progress_ledger._state.path.read_bytes(), ledger_before)
        with closing(sqlite3.connect(app.store.path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM store_metadata").fetchone()[0], store_before)
        with self.assertRaisesRegex(console.ConsoleError, "does not belong|observed project"):
            app.run_log("root", project_id="project:missing")
        with self.assertRaisesRegex(console.ConsoleError, "observed host CTRL|host-confirmed"):
            app.run_log("lead", project_id="project:alpha")

    def test_run_log_cursor_is_monotonic_bounded_and_reports_truncation(self) -> None:
        self._confirm_root_ctrl()
        app = console.App(self.codex_home, self.config)
        for index in range(205):
            self.assertEqual(app.progress_ledger.append(self._notification_event(
                f"run-{index:03d}", f"run-block-{index:03d}", "BLOCK_CREATED", "ACTIVE", index + 1,
            ))["status"], "appended")
        initial = app.run_log("root", project_id="project:alpha")
        sequences = [item["event_seq"] for item in initial["items"]]
        self.assertEqual((len(sequences), sequences[0], sequences[-1]), (200, 6, 205))
        self.assertEqual(sequences, sorted(set(sequences)))
        self.assertTrue(initial["retention"]["page_truncated"])
        self.assertEqual(initial["cursor"]["next_event_seq"], 205)

        self.assertEqual(app.progress_ledger.append(self._notification_event(
            "run-new", "run-block-new", "BLOCK_CREATED", "ACTIVE", 206,
        ))["status"], "appended")
        delta = app.run_log("root", project_id="project:alpha", after_cursor=205)
        self.assertEqual([item["event_id"] for item in delta["items"]], ["run-new"])
        self.assertEqual(delta["cursor"]["next_event_seq"], 206)
        self.assertEqual(app.run_log(
            "root", project_id="project:alpha", after_cursor=206,
        )["items"], [])

        records, _ = app._strict_run_log_records()
        with mock.patch.object(app, "_strict_run_log_records", return_value=(records[10:], True)):
            stale = app.run_log("root", project_id="project:alpha", after_cursor=1)
        self.assertTrue(stale["retention"]["source_scan_truncated"])
        self.assertTrue(stale["retention"]["stale_cursor"])
        self.assertEqual(stale["cursor"]["next_event_seq"], 206)
        with self.assertRaisesRegex(console.ConsoleError, "newer than"):
            app.run_log("root", project_id="project:alpha", after_cursor=999)

    def test_run_log_fails_closed_on_corruption_and_route_requires_exact_authorization(self) -> None:
        self._confirm_root_ctrl()
        app = console.App(self.codex_home, self.config)
        app.progress_ledger.append(self._notification_event(
            "run-one", "run-one-block", "BLOCK_CREATED", "ACTIVE", 1,
        ))
        with app.progress_ledger._state.path.open("ab") as handle:
            handle.write(b"{corrupt\n")
        with self.assertRaisesRegex(console.ConsoleError, "source Ledger is corrupt"):
            app.run_log("root", project_id="project:alpha")
        with self.assertRaisesRegex(console.ConsoleError, "non-negative"):
            app.run_log("root", project_id="project:alpha", after_cursor=-1)

        routed = console.App(self.codex_home, self.config)
        routed.run_log = mock.Mock(return_value={"ok": True, "items": []})
        rejected = self._handler(
            "127.0.0.1", "127.0.0.1:4788", origin="http://evil.example", token=routed.token,
        )
        rejected.server = SimpleNamespace(app=routed)
        rejected.path = "/api/run-log?ctrl_id=root&project_id=project%3Aalpha"
        rejected._error = mock.Mock()
        rejected._json = mock.Mock()
        rejected.do_GET()
        rejected._error.assert_called_once_with(
            console.HTTPStatus.FORBIDDEN, "run log requires local same-origin authorization",
        )
        routed.run_log.assert_not_called()

        allowed = self._handler(
            "127.0.0.1", "127.0.0.1:4788", origin="http://127.0.0.1:4788", token=routed.token,
        )
        allowed.server = SimpleNamespace(app=routed)
        allowed.path = "/api/run-log?ctrl_id=root&project_id=project%3Aalpha&agent_id=task&after_cursor=3"
        allowed._json = mock.Mock()
        allowed.do_GET()
        routed.run_log.assert_called_once_with(
            "root", project_id="project:alpha", agent_id="task", after_cursor=3,
        )

        malformed = self._handler(
            "127.0.0.1", "127.0.0.1:4788", origin="http://127.0.0.1:4788", token=routed.token,
        )
        malformed.server = SimpleNamespace(app=routed)
        malformed.path = "/api/run-log?project_id=project%3Aalpha&extra=1"
        malformed._error = mock.Mock()
        malformed._json = mock.Mock()
        malformed.do_GET()
        malformed._error.assert_called_once_with(
            console.HTTPStatus.BAD_REQUEST, "run log requires ctrl_id and bounded filters",
        )

    def test_overview_is_safe_and_hierarchical(self) -> None:
        overview = console.build_overview(self.codex_home, self.config)
        ids = {node["id"] for node in overview["nodes"]}
        self.assertIn("lead", ids)
        self.assertIn("task", ids)
        self.assertIn("review", ids)
        self.assertIn("unsafe", ids)
        self.assertIn("root", ids)
        self.assertEqual(overview["analytics"]["tasks"], 5)
        self.assertEqual(overview["analytics"]["tokens"], 1749)
        unbound = next(node for node in overview["nodes"] if node["id"] == "unsafe")
        self.assertEqual((unbound["project_id"], unbound["project_binding_state"]), ("", "UNBOUND"))
        self.assertTrue(all(project["id"].startswith("project:") for project in overview["projects"]))
        self.assertFalse(any("C:/" in json.dumps(item) for item in overview["projects"]))
        self.assertIn({"source": "lead", "target": "task", "relationship": "delegated", "status": "open"}, overview["links"])
        self.assertIn({"source": "root", "target": "lead", "relationship": "delegated", "status": "open"}, overview["links"])
        observed_edges = {("root", "lead"), ("lead", "task"), ("lead", "review")}
        self.assertTrue(all((link["source"], link["target"]) in observed_edges for link in overview["links"]))
        ctrl = next(node for node in overview["nodes"] if node["id"] == "root")
        self.assertEqual((ctrl["role"], ctrl["icon"]), ("ctrl", "🐙"))
        self.assertEqual(next(node for node in overview["nodes"] if node["id"] == "review")["status"], "done")
        self.assertGreaterEqual(overview["observation_window_ms"], 24 * 60 * 60 * 1000)
        self.assertEqual(overview["controllers"][0]["id"], "root")
        self.assertEqual(next(node for node in overview["nodes"] if node["id"] == "task")["controller_ids"], ["root"])
        self.assertTrue(all(node["role_label"] == "TASK" for node in overview["nodes"] if node["role"] != "ctrl"))
        self.assertEqual(next(node for node in overview["nodes"] if node["id"] == "review")["worker_role"], "REVIEW")
        self.assertEqual(ctrl["proof_snapshot"]["state"], "UNAVAILABLE")
        self.assertIn("host activity is not proof", ctrl["proof_snapshot"]["claim_limit"].lower())
        self.assertLess(overview["performance"]["data_bytes"], overview["performance"]["budget"]["data_bytes"])
        self.assertEqual(overview["performance"]["budget"]["cache_hit_ms"], 5)

    def test_topology_loading_and_empty_states_never_fabricate_records(self) -> None:
        base = console.build_overview(self.codex_home, self.config)["topology"]
        self.assertEqual((base["state"], base["loading"], base["empty"]), ("LOADING", True, True))
        self.assertEqual((base["nodes"], base["tasks"], base["agent_edges"], base["task_edges"]), ([], [], [], []))

        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DELETE FROM thread_spawn_edges")
            connection.execute("DELETE FROM threads")
            connection.commit()
        projected = console.App(self.codex_home, self.config).overview()["topology"]
        self.assertEqual((projected["state"], projected["loading"], projected["empty"]), ("EMPTY", False, True))
        self.assertEqual((projected["nodes"], projected["tasks"], projected["roots"]), ([], [], []))

    def test_independent_host_tasks_keep_exact_projects_neutral_identity_and_restart_counts(self) -> None:
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("ALTER TABLE threads ADD COLUMN project_id TEXT")
            for index in range(1, 22):
                project_id = "project:helm" if index == 1 else "project:rightwork" if index == 2 else f"project:extra-{index:02d}"
                connection.execute(
                    "INSERT INTO projects VALUES (?,?,?,?,?,?)",
                    (project_id, project_id.split(":", 1)[1], "{}", index, 0, 0),
                )
            now = 2_000_000_100_000
            rows = (
                ("helm-designer", "🎨DESIGNER - Helm shell", "project:helm"),
                ("helm-architect", "🐙CTRL - Not admitted", "project:helm"),
                ("rightwork-agent", "🧭LEAD - RightWork", "project:rightwork"),
                ("projectless-agent", "🐙CTRL - Projectless", None),
            )
            for offset, (thread_id, title, project_id) in enumerate(rows, 1):
                connection.execute(
                    "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        thread_id, title, "C:/unbound/task", now // 1000, now // 1000,
                        now, now + offset, "gpt-5.6-sol", "high", 1, 0, "", "main",
                        "", "", "", 0, project_id,
                    ),
                )
            connection.executemany(
                "INSERT INTO thread_spawn_edges VALUES (?,?,?)",
                [
                    ("helm-designer", "helm-architect", "open"),
                    ("rightwork-agent", "projectless-agent", "closed"),
                ],
            )
            connection.commit()

        first = console.App(self.codex_home, self.config).overview()
        restarted = console.App(self.codex_home, self.config).overview()
        self.assertEqual(len(first["projects"]), 22)
        self.assertEqual([project["id"] for project in first["projects"]], [project["id"] for project in restarted["projects"]])
        by_id = {node["id"]: node for node in first["nodes"]}
        for node_id, project_id in (
            ("helm-designer", "project:helm"),
            ("helm-architect", "project:helm"),
            ("rightwork-agent", "project:rightwork"),
        ):
            node = by_id[node_id]
            self.assertEqual((node["node_kind"], node["project_id"]), ("independent_host_task", project_id))
            self.assertEqual((node["role"], node["structural_role"], node["manifest_identity"]), ("independent", None, None))
            self.assertEqual((node["artifact"], node["worker"]), ("Codex task", ""))
            self.assertEqual(node["presentation"], console.INDEPENDENT_HOST_PRESENTATION)
            self.assertEqual(node["actions"], {"open_detail": True, "edit_manifest": False, "role_actions": False})
            self.assertFalse(node["execution_authority"] or node["swarm_authority"])
        projectless = by_id["projectless-agent"]
        self.assertEqual((projectless["project_id"], projectless["project_binding_state"]), ("", "UNBOUND"))
        helm = next(project for project in first["projects"] if project["id"] == "project:helm")
        rightwork = next(project for project in first["projects"] if project["id"] == "project:rightwork")
        self.assertEqual((helm["task_count"], helm["independent_count"]), (2, 2))
        self.assertEqual((rightwork["task_count"], rightwork["independent_count"]), (1, 1))
        self.assertEqual(first["analytics"]["independent_count"], restarted["analytics"]["independent_count"])
        self.assertEqual(first["topology"]["independent_nodes"], restarted["topology"]["independent_nodes"])
        self.assertEqual(first["topology"]["independent_count"], restarted["topology"]["independent_count"])
        self.assertIn(
            ("helm-designer", "helm-architect", "HOST_SPAWN"),
            [(edge["source"], edge["target"], edge["edge_kind"]) for edge in first["topology"]["host_edges"]],
        )
        self.assertTrue(all(not edge["execution_authority"] and not edge["swarm_authority"] for edge in first["topology"]["host_edges"]))
        self.assertNotIn("projectless-agent", {edge["target"] for edge in first["topology"]["host_edges"]})
        self.assertFalse(first["controllers"])

    def test_overview_project_briefs_projects_generic_digest_bound_root_without_product_branch(self) -> None:
        root = self.root / "nemo-root"
        self._write_project_brief(root, "nemo")
        project_id = "local-7df124335c46ab55d00ad4f754a3e26a"
        self._add_host_project(project_id, "Nemo", str(root))
        for index in range(20):
            self._add_host_project(f"project:saved-{index:02d}", f"saved-{index:02d}", str(self.root / f"missing-{index:02d}"))

        first = console.App(self.codex_home, self.config).overview()["project_briefs"]
        restarted = console.App(self.codex_home, self.config).overview()["project_briefs"]
        self.assertEqual((first["state"], first["available"], len(first["projects"])), ("KNOWN", True, 22))
        nemo = next(project for project in first["projects"] if project["project_id"] == project_id)
        self.assertEqual((nemo["display_name"], nemo["root_binding_status"], nemo["status"]), ("Nemo", "KNOWN", "KNOWN"))
        self.assertRegex(nemo["digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            set(nemo),
            {"project_id", "display_name", "root_binding_status", "status", "digest", "path", "source"},
        )
        self.assertEqual(first, restarted)
        order = [project["project_id"] for project in first["projects"]]

        self._write_project_brief(root, "nemo", links=[{"kind": "digest-change"}])
        changed = console.App(self.codex_home, self.config).overview()["project_briefs"]
        changed_restart = console.App(self.codex_home, self.config).overview()["project_briefs"]
        self.assertNotEqual(first["cursor"], changed["cursor"])
        self.assertNotEqual(nemo["digest"], next(
            project["digest"] for project in changed["projects"] if project["project_id"] == project_id
        ))
        self.assertEqual(changed, changed_restart)

        valid_text = root.joinpath("SWARM.md").read_text(encoding="utf-8")
        root.joinpath("SWARM.md").write_text("not a project brief\n", encoding="utf-8")
        invalid = console.App(self.codex_home, self.config).overview()["project_briefs"]
        self.assertEqual(next(
            project["status"] for project in invalid["projects"] if project["project_id"] == project_id
        ), "INVALID")
        self.assertNotEqual(changed["cursor"], invalid["cursor"])

        root.joinpath("SWARM.md").write_text(valid_text + "\n" + valid_text, encoding="utf-8")
        ambiguous = console.App(self.codex_home, self.config).overview()["project_briefs"]
        self.assertEqual(next(
            project["status"] for project in ambiguous["projects"] if project["project_id"] == project_id
        ), "AMBIGUOUS")
        self.assertNotEqual(invalid["cursor"], ambiguous["cursor"])

        root.joinpath("SWARM.md").unlink()
        missing = console.App(self.codex_home, self.config).overview()["project_briefs"]
        missing_restart = console.App(self.codex_home, self.config).overview()["project_briefs"]
        self.assertEqual(next(
            project["status"] for project in missing["projects"] if project["project_id"] == project_id
        ), "MISSING")
        self.assertNotEqual(ambiguous["cursor"], missing["cursor"])
        self.assertEqual(missing, missing_restart)
        self.assertTrue(all(
            [project["project_id"] for project in projection["projects"]] == order
            for projection in (changed, invalid, ambiguous, missing)
        ))
        self.assertNotIn(project_id, SERVER.read_text(encoding="utf-8"))

    def test_root_brief_lenses_project_through_existing_registry_without_product_branch(self) -> None:
        root = self.root / "portable-root"
        runtime_id = "local-portable-runtime-id"
        lens_ids = [
            "lens-overview-health", "lens-roadmap-milestones", "lens-tasks-kanban",
            "lens-flow-architecture", "lens-artifacts-proof", "lens-agents",
        ]
        self._write_project_brief(
            root,
            "portable",
            proposed_lens_ids=lens_ids,
            extra={
                "objective": {"current": "Project one accepted model", "ranked_outcomes": []},
                "tasks": [],
                "artifacts": [],
                "authority": {"ctrl_id": "ctrl-portable"},
                "ownership": {"active_ctrl_id": "ctrl-portable", "active_lead_ids": []},
            },
        )
        self._add_host_project(runtime_id, "portable", str(root))
        app = console.App(self.codex_home, self.config, self.root / "console" / "portable.sqlite3")

        briefs = app._project_briefs_projection()
        stale_briefs = copy.deepcopy(briefs)
        next(item for item in stale_briefs["projects"] if item["project_id"] == runtime_id)["digest"] = "sha256:" + "0" * 64
        fresh = console.App(self.codex_home, self.config, self.root / "console" / "portable-fresh.sqlite3")
        self.assertIsNone(fresh._project_view_projection(runtime_id, stale_briefs))

        projection = app._project_view_projection(runtime_id, briefs)
        self.assertIsNotNone(projection)
        self.assertEqual((projection["project_id"], projection["model_project_id"]), (runtime_id, "portable"))
        self.assertEqual(projection["tab"], {"id": "ui", "label": "Workspace"})
        self.assertEqual([view["id"] for view in projection["views"]], [
            "view.project.overview-health", "view.project.roadmap", "view.project.work",
            "view.project.flow", "view.project.artifacts", "view.project.agents",
        ])
        self.assertEqual(projection["views"], projection["tabs"])
        self.assertEqual(projection["projection_binding"]["project_id"], runtime_id)
        self.assertEqual(projection["projection_binding"]["model_project_id"], "portable")
        self.assertEqual(projection["projection_binding"]["locator"], None)
        self.assertRegex(projection["projection_binding"]["brief_bytes_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(projection["accepted_cursor"]["digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertTrue(all(
            source["source_digest"].startswith("sha256:")
            for view in projection["views"] for source in view["sources"]
        ))
        self.assertNotIn(runtime_id, SERVER.read_text(encoding="utf-8"))

        self._write_project_brief(root, "portable", proposed_lens_ids=["future-lens"])
        self.assertIsNone(app._project_view_projection(runtime_id))

    def test_root_brief_lenses_withhold_invalid_sources_and_retain_last_good_on_invalid_root(self) -> None:
        root = self.root / "conditional-root"
        runtime_id = "project:conditional"
        self._write_project_brief(
            root,
            runtime_id,
            proposed_lens_ids=["lens-overview-health", "lens-roadmap-milestones"],
        )
        self._add_host_project(runtime_id, "conditional", str(root))
        app = console.App(self.codex_home, self.config, self.root / "console" / "conditional.sqlite3")
        accepted = app._project_view_projection(runtime_id)
        self.assertEqual([view["id"] for view in accepted["views"]], [
            "view.project.overview-health", "view.project.roadmap",
        ])

        self._write_project_brief(
            root,
            runtime_id,
            proposed_lens_ids=["lens-overview-health", "lens-roadmap-milestones"],
            extra={"milestones": "invalid"},
        )
        stale = app._project_view_projection(runtime_id)
        self.assertEqual(stale["status"], "STALE_LAST_ACCEPTED")
        self.assertEqual(stale["projection_binding"], accepted["projection_binding"])
        self.assertEqual(stale["source_digest"], accepted["source_digest"])
        self.assertEqual(stale["views"], accepted["views"])

        fresh = console.App(self.codex_home, self.config, self.root / "console" / "conditional-fresh.sqlite3")
        self.assertIsNone(fresh._project_view_projection(runtime_id))

        self._write_project_brief(
            root,
            runtime_id,
            proposed_lens_ids=["lens-overview-health", "lens-roadmap-milestones"],
            extra={"objective": {"current": "Recovered accepted model", "ranked_outcomes": []}},
        )
        recovered = app._project_view_projection(runtime_id)
        self.assertNotEqual(recovered["source_digest"], accepted["source_digest"])
        self.assertNotIn("status", recovered)
        self.assertEqual(recovered["views"][0]["content"]["blocks"][0]["text"], "Recovered accepted model")

        other_root = self.root / "cross-project-root"
        self._write_project_brief(other_root, "other", proposed_lens_ids=["lens-overview-health"])
        self._add_host_project("project:cross", "cross", str(other_root))
        self.assertIsNone(app._project_view_projection("project:cross"))

    def test_manifest_topology_has_exact_ports_task_limit_and_restart_stability(self) -> None:
        self._confirm_root_ctrl()
        app = console.App(self.codex_home, self.config)
        self._append_topology_manifests(app)
        raw_topology = app.progress_ledger.project_topology("project:alpha", "root")
        raw_node_ids = {node["node_id"] for node in raw_topology["nodes"]}
        self.assertTrue({f"work-block-{index}" for index in range(1, 5)} <= raw_node_ids)
        self.assertFalse({"lead", "task", *(f"work-{index}" for index in range(1, 5))} & raw_node_ids)
        self.assertFalse(
            {
                *(f"agent-manifest-{index}" for index in range(1, 4)),
                *(f"task-manifest-{index}" for index in range(1, 5)),
            }
            & set(raw_topology["source_event_ids"])
        )
        for index in range(4):
            update = self._notification_event(
                f"work-update-{index + 1}", f"work-block-{index + 1}",
                "CURRENT_ACTION_CHANGED", "ACTIVE", 200 + index,
                parent_event_id=f"work-event-{index + 1}", milestone_id=f"work-milestone-{index + 1}",
            )
            update.update(
                task_id=f"work-{index + 1}", owner_id="root", ctrl_id="root",
                material_update_sentence="🧨 hostile caller prose " + "界" * 100,
            )
            app.progress_ledger.append(update)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE threads SET title = '🧨 hostile raw title' WHERE id = 'root'")
            connection.execute("UPDATE threads SET title = '🧪 another raw title' WHERE id = 'task'")
            connection.commit()

        with mock.patch.object(
            app.progress_ledger, "project_topology",
            side_effect=AssertionError("Overview consumed raw Ledger topology"),
        ):
            topology = app.overview()["topology"]
        self.assertEqual((topology["state"], topology["loading"], topology["empty"]), ("KNOWN", False, False))
        by_id = {node["id"]: node for node in topology["nodes"]}
        self.assertEqual(set(by_id), {"root", "lead", "task"})
        self.assertFalse(any(node_id.startswith(("agent-manifest:", "task-manifest:")) for node_id in by_id))
        self.assertEqual((by_id["root"]["display_name"], by_id["root"]["title"]), ("CTRL", "SWARM HQ"))
        self.assertNotIn("🧨", json.dumps(topology, ensure_ascii=False))
        self.assertEqual([child["id"] for child in topology["roots"][0]["children"]], ["lead"])
        self.assertEqual(
            [child["id"] for child in topology["roots"][0]["children"][0]["children"]],
            ["task"],
        )
        self.assertFalse(by_id["root"]["royal_line"])
        self.assertTrue(by_id["lead"]["royal_line"])
        self.assertFalse(by_id["task"]["royal_line"])
        manager = next(role for role in app.builtin_role_manifests if role["id"] == "manager")
        self.assertEqual(by_id["root"]["lucide_icon"], manager["lucide_icon"])
        live = by_id["root"]["live_projection"]
        self.assertEqual((live["state"], live["mini_update"]), ("KNOWN", "Current action updated · Active"))
        self.assertEqual(len(live["context_rows"]), 3)
        self.assertTrue(all(len(row["text"]) <= 64 for row in live["context_rows"]))
        self.assertNotIn("hostile caller prose", json.dumps(live, ensure_ascii=False))
        self.assertEqual(live["context_rows"][0]["identity"], {
            "agent_id": "root", "agent_manifest_id": "agent-manifest:root",
            "task_id": "work-4", "task_manifest_id": "task-manifest:work-4",
            "role_manifest_id": "manager", "role_manifest_version": manager["version"],
        })

        self.assertEqual(by_id["root"]["task_ids"], ["work-2", "work-3", "work-1"])
        self.assertEqual((by_id["root"]["visibleTaskCount"], by_id["root"]["hiddenTaskCount"]), (3, 1))
        self.assertEqual(topology["hiddenTaskCount"], 1)
        self.assertEqual([task["task_id"] for task in topology["hidden_tasks"]], ["work-4"])
        self.assertEqual(topology["hidden_tasks"][0]["owning_agent_id"], "root")
        self.assertEqual(topology["hidden_tasks"][0]["ports"], [])
        self.assertEqual(app._scope_topology_projection(topology, "project:other")["hidden_tasks"], [])
        self.assertEqual(app._scope_topology_projection(topology, "project:alpha", "lead")["hidden_tasks"], [])
        self.assertEqual(app._scope_topology_projection(topology, "project:alpha", "root")["hidden_tasks"], topology["hidden_tasks"])
        self.assertEqual([task["task_id"] for task in topology["tasks"]], ["work-2", "work-3", "work-1"])
        self.assertEqual(len(topology["task_edges"]), 3)
        self.assertFalse({task["task_id"] for task in topology["tasks"]} & set(by_id))
        self.assertTrue(all("structural_role" not in task and "avatar" not in task and "lucide_icon" not in task for task in topology["tasks"]))
        self.assertTrue(all("progress" not in node for node in topology["nodes"]))

        records = {**by_id, **{task["id"]: task for task in topology["tasks"]}}
        port_ids: list[str] = []
        for edge in [*topology["agent_edges"], *topology["task_edges"]]:
            self.assertIn(edge["source_port_id"], records[edge["source"]]["output_port_ids"])
            self.assertIn(edge["target_port_id"], records[edge["target"]]["input_port_ids"])
            port_ids.extend((edge["source_port_id"], edge["target_port_id"]))
        self.assertEqual(len(port_ids), len(set(port_ids)))
        for node in topology["nodes"]:
            expected_inputs = int(node["parent_relation"]["state"] == "KNOWN")
            expected_outputs = len(node["children_ids"]) + node["visibleTaskCount"]
            self.assertEqual((len(node["input_port_ids"]), len(node["output_port_ids"])), (expected_inputs, expected_outputs))
            self.assertEqual(node["port_count"], expected_inputs + expected_outputs)
        self.assertTrue(all((len(task["input_port_ids"]), len(task["output_port_ids"]), task["port_count"]) == (1, 0, 1) for task in topology["tasks"]))

        restarted = console.App(self.codex_home, self.config).overview()["topology"]
        self.assertEqual(restarted, topology)

    def test_topology_current_milestone_joins_live_scope_and_manifest_on_restart(self) -> None:
        self._confirm_root_ctrl()
        app = console.App(self.codex_home, self.config)
        self._append_topology_manifests(app, task_count=1)
        with mock.patch.object(console.time, "time", return_value=1):
            overview = app.overview()
            current = overview["progress"]["projects"]["project:alpha"]["current_milestone"]
            self.assertEqual((current["state"], current["name"], current["milestone_id"], current["task_id"]),
                             ("KNOWN", "Active work", "work-milestone-1", "work-1"))
            self.assertEqual((current["project_id"], current["ctrl_id"], current["scope_version"]),
                             ("project:alpha", "root", 1))
            self.assertEqual(current["event_cursor"]["event_id"], "work-event-1")
            self.assertTrue(current["manifest_identity"]["manifest_digest"])
            for scope in ("project:alpha", "ctrl:root"):
                scoped = app._project_view(overview, scope)
                result = scoped["progress"]["projects"]["project:alpha"]["current_milestone"]
                self.assertEqual(result["name"], current["name"])
                self.assertEqual(result["cursor"], scoped["topology"]["cursor"])
            restarted = console.App(self.codex_home, self.config)
            self.assertEqual(restarted.overview()["progress"]["projects"]["project:alpha"]["current_milestone"], current)
            foreign = copy.deepcopy(overview["topology"]["tasks"][0])
            foreign["ctrl_id"] = "other-ctrl"
            mixed = copy.deepcopy(overview)
            mixed["topology"]["hidden_tasks"].append(foreign)
            progress = app._progress_payload(mixed)
            self.assertEqual(progress["projects"]["project:alpha"]["current_milestone"]["state"], "UNKNOWN")
            self.assertEqual(progress["controllers"]["root"]["current_milestone"]["name"], "Active work")
            for changed in ("PARTIAL", "UNKNOWN"):
                mixed["topology"] = copy.deepcopy(overview["topology"])
                mixed["topology"]["state"] = changed
                self.assertEqual(app._progress_payload(mixed)["projects"]["project:alpha"]["current_milestone"]["state"], "UNKNOWN")
        with mock.patch.object(console.time, "time", return_value=0.01):
            self.assertEqual(app._progress_payload(overview)["projects"]["project:alpha"]["current_milestone"]["state"], "UNKNOWN")

        # Retained activity is not a fresh current milestone indefinitely.
        stale = app._project_view(overview, None)["progress"]["projects"]["project:alpha"]["current_milestone"]
        self.assertEqual((stale["state"], stale["name"], stale["reason"]),
                         ("UNKNOWN", None, "STALE_MILESTONE"))
        self.assertEqual(overview["progress"]["projects"]["project:alpha"]["current_milestone"]["state"], "KNOWN")
        with mock.patch.object(console.time, "time", return_value=1):
            for kind, state, stamp, admitted in (("STATE_CHANGED", "REVIEW", 110, 0),
                                                 ("PROOF_ADMITTED", "VERIFIED", 111, 1),
                                                 ("ACCEPTED", "ACCEPTED", 112, 1)):
                event = self._notification_event(
                    f"milestone-{stamp}", "work-block-1", kind, state, stamp,
                    milestone_id="work-milestone-1", admitted_proof_weight=admitted,
                    proof_receipt_ids=["proof"] if admitted else [],
                )
                event.update(task_id="work-1", owner_id="root")
                app.progress_ledger.append(event)
            view = app._decorate_overview(app._host_overview())
            self.assertEqual(view["progress"]["projects"]["project:alpha"]["current_milestone"]["state"], "UNKNOWN")
            # Even a valid retained block ID cannot borrow a different milestone's label.
            event = self._notification_event("wrong-milestone", "work-block-1", "REWORK_REQUESTED",
                                             "INVALIDATED_REWORK", 113, milestone_id="other-milestone")
            event.update(task_id="work-1", owner_id="root")
            app.progress_ledger.append(event)
            self.assertEqual(app._topology_projection(app._host_overview())["tasks"], [])

    def test_topology_current_milestone_ambiguity_includes_hidden_tasks(self) -> None:
        self._confirm_root_ctrl()
        app = console.App(self.codex_home, self.config)
        self._append_topology_manifests(app)
        with mock.patch.object(console.time, "time", return_value=1):
            overview = app.overview()
            current = overview["progress"]["projects"]["project:alpha"]["current_milestone"]
            self.assertEqual((current["state"], current["name"], current["reason"]),
                             ("UNKNOWN", None, "AMBIGUOUS_CURRENT_MILESTONE"))
            self.assertEqual(len(overview["topology"]["hidden_tasks"]), 1)
            # A hidden candidate cannot be lost when visible tasks are completed.
            for task in overview["topology"]["tasks"]:
                for block in task["blocks"]:
                    block["lifecycle_state"] = "ACCEPTED"
            current = app._progress_payload(overview)["projects"]["project:alpha"]["current_milestone"]
            self.assertEqual(current["task_id"], overview["topology"]["hidden_tasks"][0]["task_id"])

    def test_topology_task_progress_includes_completed_scope_and_live_blocks(self) -> None:
        self._confirm_root_ctrl()
        app = console.App(self.codex_home, self.config)
        self._append_topology_manifests(app, task_count=0)
        manifest = build_task_manifest(
            manifest_id="manifest:whole", task_id="whole", task_name="Whole task",
            project_id="project:alpha", ctrl_id="root",
            milestones=[{"milestone_id": "m", "order": 0, "title": "Delivery",
                         "verification_policy": "source-contract", "supersedes_milestone_id": None}],
            blocks=[{"block_id": name, "milestone_id": "m", "order": index, "title": name,
                     "verification_policy": "source-contract", "estimate_minutes": None,
                     "weight": None, "supersedes_block_id": None}
                    for index, name in enumerate(("done", "active", "removed"))],
        )
        app.progress_ledger.append(identity_manifest_event(
            manifest, event_id="whole-manifest", dedupe_key="whole-manifest",
            observed_at_ms=10, provenance="test exact task scope",
        ))

        def append(name, kind, state, stamp, admitted=0, weight=1):
            event = self._notification_event(
                f"{name}-{stamp}", name, kind, state, stamp, milestone_id="m",
                committed_weight=weight, admitted_proof_weight=admitted,
                proof_receipt_ids=["accepted-proof"] if admitted else [],
            )
            event.update(task_id="whole", owner_id="root")
            app.progress_ledger.append(event)

        for index, name in enumerate(("done", "active", "removed")):
            append(name, "BLOCK_CREATED", "ACTIVE", 20 + index)
        append("done", "STATE_CHANGED", "REVIEW", 30)
        append("done", "PROOF_ADMITTED", "VERIFIED", 31, 1)
        append("done", "ACCEPTED", "ACCEPTED", 32, 1)
        append("removed", "TOMBSTONED", "TOMBSTONED", 33)
        view = app._host_overview(refresh=True)
        topology = app._topology_projection(view)
        task = topology["tasks"][0]
        self.assertEqual((task["task_id"], task["owning_agent_id"], task["state"], task["progress"]),
                         ("whole", "root", "ACTIVE", 50.0))
        self.assertEqual([(b["block_id"], b["lifecycle_state"], b["progress"]) for b in task["blocks"]],
                         [("done", "ACCEPTED", 100.0), ("active", "ACTIVE", 0.0)])
        self.assertEqual(task["event_cursor"]["event_id"], "done-32")
        foreign = self._notification_event("foreign", "foreign-block", "BLOCK_CREATED", "ACTIVE", 34,
                                           committed_weight=100)
        foreign.update(task_id="whole", owner_id="root", ctrl_id="other-ctrl")
        app.progress_ledger.append(foreign)
        self.assertEqual(app._topology_projection(view)["tasks"][0]["progress"], 50.0)
        self.assertTrue(all(b["task_id"] == "whole" and b["project_id"] == "project:alpha"
                            and b["ctrl_id"] == "root" and b["event_cursor"]["event_digest"]
                            for b in task["blocks"]))
        # Never borrow the owning agent's ETA for another task.
        view["nodes"][0]["eta"] = {"project_id": "project:alpha", "eta_source": "task_owner_report", "eta_end_ms": 99}
        self.assertEqual(app._topology_projection(view)["tasks"][0]["eta"]["status"], "UNKNOWN")
        view["nodes"].append({"id": "whole", "project_id": "project:alpha", "eta": {
            "project_id": "project:alpha", "eta_source": "task_owner_report", "status": "in_progress",
            "eta_start_ms": 100, "eta_end_ms": 200, "eta_observed_at_ms": 90, "revision": 2,
        }})
        eta = app._topology_projection(view)["tasks"][0]["eta"]
        self.assertEqual((eta["task_id"], eta["project_id"], eta["eta_end_ms"], eta["revision"]),
                         ("whole", "project:alpha", 200, 2))
        view["nodes"][-1]["eta"]["project_id"] = "project:other"
        self.assertEqual(app._topology_projection(view)["tasks"][0]["eta"]["status"], "UNKNOWN")
        restarted = console.App(self.codex_home, self.config)
        self.assertEqual(restarted._topology_projection(app._host_overview(refresh=True))["tasks"], topology["tasks"])
        append("active", "REWORK_REQUESTED", "INVALIDATED_REWORK", 40)
        self.assertEqual(app._topology_projection(view)["tasks"][0]["blocks"][1]["lifecycle_state"], "INVALIDATED_REWORK")
        event = self._notification_event("unmeasured", "active", "STATE_CHANGED", "ACTIVE", 41, milestone_id="m")
        event.update(task_id="whole", owner_id="root")
        event["measurement"] = {"state": "UNMEASURED", "committed_weight": None, "admitted_proof_weight": 0, "basis_receipt_ids": []}
        app.progress_ledger.append(event)
        self.assertNotIn("progress", app._topology_projection(view)["tasks"][0])

    def test_topology_promotes_only_connector_confirmed_task_creation_binding(self) -> None:
        self._confirm_root_ctrl()
        app = console.App(self.codex_home, self.config)
        self._append_topology_manifests(app, task_count=0)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "bound-agent", "private host title", "C:/work/alpha", 2_000_000_000,
                    2_000_000_000, 2_000_000_000_000, 2_000_000_000_001,
                    "gpt-5.6-terra", "high", 0, 0, "", "main", "", "", "", 0,
                ),
            )
            connection.commit()

        role = next(item for item in app.builtin_role_manifests if item["id"] == "developer")
        manifest = build_task_manifest(
            manifest_id="task-manifest:bound-agent", task_id="bound-agent",
            task_name="Topology implementation", project_id="project:alpha", ctrl_id="root",
            role_scope="DOER_SINGLE",
            milestones=[{
                "milestone_id": "bound-milestone", "order": 0, "title": "Implementation",
                "verification_policy": "source-contract", "supersedes_milestone_id": None,
            }],
            blocks=[{
                "block_id": "bound-block", "milestone_id": "bound-milestone", "order": 0,
                "title": "Build the bounded slice", "verification_policy": "source-contract",
                "estimate_minutes": 30, "weight": None, "supersedes_block_id": None,
            }],
        )
        connector = {
            "schema_version": 1, "record_type": "CONNECTOR", "command_id": "command:create-bound",
            "idempotency_key": "create-bound", "command_digest": "a" * 64,
            "project_id": "project:alpha", "root_digest": "b" * 64,
            "action": "MANUAL_AGENT", "thread_id": None, "turn_id": None,
            "observed_root_digest": None,
        }
        app.progress_ledger.append_connector_receipt({
            **connector, "receipt_id": "create-bound:command", "receipt_index": 0,
            "status": "COMMAND", "observed_at_ms": 1,
        })
        app.progress_ledger.append_connector_receipt({
            **connector, "receipt_id": "create-bound:ack", "receipt_index": 1,
            "status": "ACKNOWLEDGED", "thread_id": "bound-agent",
            "observed_root_digest": "b" * 64, "observed_at_ms": 2,
        })
        result = {
            **connector, "receipt_id": "create-bound:result", "receipt_index": 2,
            "status": "RESULT", "thread_id": "bound-agent", "turn_id": "turn:bound-agent",
            "observed_root_digest": "b" * 64, "observed_at_ms": 3,
        }
        binding = task_creation_binding_event(
            operation_id="create-bound", project_id="project:alpha", root_digest="b" * 64,
            ctrl_id="root", task_id="bound-agent", role_manifest=role, task_manifest=manifest,
            parent_task_id="root", topology_manifest_receipt_id="create-bound:topology",
            task_receipt_id="create-bound:task",
            milestone_receipts=[{"id": "bound-milestone", "receipt_id": "receipt:bound-milestone"}],
            block_receipts=[{"id": "bound-block", "receipt_id": "receipt:bound-block"}],
            explicit_empty_work_receipt_id=None, host_result_receipt_id="create-bound:result",
            observed_at_ms=4,
        )
        assert binding is not None
        app.progress_ledger.append_connector_result_with_task_creation(result, binding)

        overview = app.overview()
        topology = overview["topology"]
        node = next(item for item in topology["nodes"] if item["id"] == "bound-agent")
        public_node = next(item for item in overview["nodes"] if item["id"] == "bound-agent")
        self.assertEqual(
            (node["profession"], node["structural_role"], node["parent_relation"]["state"]),
            ("developer", "DOER", "KNOWN"),
        )
        self.assertEqual(node["manifest_identity"]["identity_kind"], "TASK_CREATION_BINDING")
        self.assertEqual(node["creation_binding"]["operation_id"], "create-bound")
        self.assertEqual((node["initial_work"]["state"], node["initial_work"]["blocks"][0]["block_id"]), ("KNOWN", "bound-block"))
        self.assertEqual((public_node["artifact"], public_node["worker"]), ("Topology implementation", ""))
        self.assertNotIn("private host title", json.dumps(overview))
        self.assertNotIn("bound-agent", {item["id"] for item in topology["independent_nodes"]})
        self.assertIn(("root", "bound-agent"), {(edge["source"], edge["target"]) for edge in topology["agent_edges"]})
        self.assertEqual(console.App(self.codex_home, self.config).overview()["topology"], topology)

    def test_topology_ambiguous_and_cycle_edges_fail_closed_without_ports(self) -> None:
        self._confirm_root_ctrl()
        self._add_same_project_ctrl()
        app = console.App(self.codex_home, self.config)
        self._append_topology_manifests(app, task_count=1, include_review=True)
        roles = {manifest["id"]: manifest for manifest in app.builtin_role_manifests}
        for index, (agent_id, display_name, profession, structural_role) in enumerate((
            ("other-ctrl", "Amber", "manager", "CTRL"),
            ("other-task", "Azure", "developer", "DOER"),
        ), 1):
            manifest = build_agent_manifest(
                manifest_id=f"agent-manifest:{agent_id}", agent_id=agent_id,
                project_id="project:alpha", ctrl_id="other-ctrl", display_name=display_name,
                title=f"Valid branch {index}", profession=profession, structural_role=structural_role,
                avatar_selection="canonical", role_manifest_ref=role_manifest_reference(roles[profession]),
            )
            app.progress_ledger.append(identity_manifest_event(
                manifest, event_id=f"mixed-agent-{index}", dedupe_key=f"mixed-agent-{index}-dedupe",
                observed_at_ms=60 + index, provenance="console topology fixture",
            ))
        base = console.build_overview(self.codex_home, self.config)

        closed = app._topology_projection(base)
        closed_by_id = {node["id"]: node for node in closed["nodes"]}
        self.assertEqual(closed_by_id["review"]["parent_relation"]["reason"], "UNSUPPORTED_EDGE_STATUS")
        self.assertEqual(closed_by_id["review"]["input_port_ids"], [])
        self.assertNotIn("review", {edge["target"] for edge in closed["agent_edges"]})

        ambiguous = copy.deepcopy(base)
        ambiguous["links"] = [
            {"source": "root", "target": "lead", "status": "open"},
            {"source": "root", "target": "task", "status": "open"},
            {"source": "lead", "target": "task", "status": "open"},
            {"source": "lead", "target": "review", "status": "open"},
        ]
        projected = app._topology_projection(ambiguous)
        by_id = {node["id"]: node for node in projected["nodes"]}
        self.assertEqual((projected["state"], by_id["task"]["parent_relation"]["reason"]), ("PARTIAL", "AMBIGUOUS_PARENT"))
        self.assertFalse(by_id["task"]["royal_line"])
        self.assertEqual(by_id["task"]["input_port_ids"], [])
        self.assertNotIn("task", {edge["target"] for edge in projected["agent_edges"]})

        cyclic = copy.deepcopy(base)
        cyclic["links"] = [
            {"source": "root", "target": "lead", "status": "open"},
            {"source": "lead", "target": "task", "status": "open"},
            {"source": "task", "target": "root", "status": "open"},
            {"source": "lead", "target": "review", "status": "open"},
            {"source": "other-ctrl", "target": "other-task", "status": "open"},
        ]
        projected = app._topology_projection(cyclic)
        by_id = {node["id"]: node for node in projected["nodes"]}
        self.assertEqual({by_id[node_id]["parent_relation"]["reason"] for node_id in ("root", "lead", "task")}, {"CYCLE"})
        self.assertEqual(by_id["review"]["parent_relation"]["reason"], "ANCESTOR_CYCLE")
        self.assertTrue(all(not by_id[node_id]["royal_line"] for node_id in ("root", "lead", "task")))
        self.assertFalse({"root", "lead", "task", "review"} & {edge["target"] for edge in projected["agent_edges"]})
        self.assertTrue(all(not by_id[node_id]["ports"] for node_id in ("root", "lead", "task", "review")))
        self.assertFalse(projected["tasks"])
        self.assertFalse(projected["task_edges"])
        self.assertTrue(all(by_id[node_id]["hierarchy_membership"] == "INVALID" for node_id in ("root", "lead", "task", "review")))
        self.assertFalse({"root", "lead", "task", "review"} & {node["id"] for node in projected["orphans"]})
        self.assertEqual([root["id"] for root in projected["roots"]], ["other-ctrl"])
        self.assertEqual([child["id"] for child in projected["roots"][0]["children"]], ["other-task"])
        scoped = app._scope_topology_projection(projected, "project:alpha", "root")
        self.assertEqual((scoped["state"], scoped["reason"]), ("PARTIAL", "MISSING_OR_CONFLICTING_BINDING"))
        self.assertEqual([node["id"] for node in scoped["nodes"]], ["root"])
        self.assertFalse(scoped["tasks"] or scoped["agent_edges"] or scoped["task_edges"])

    def test_topology_preserves_multiple_manifest_ctrl_roots_in_stable_order(self) -> None:
        self._confirm_root_ctrl()
        self._add_same_project_ctrl()
        app = console.App(self.codex_home, self.config)
        self._append_topology_manifests(app, task_count=0)
        manager = next(role for role in app.builtin_role_manifests if role["id"] == "manager")
        other = build_agent_manifest(
            manifest_id="agent-manifest:other-ctrl", agent_id="other-ctrl",
            project_id="project:alpha", ctrl_id="other-ctrl", display_name="Amber",
            title="Second command", profession="manager", structural_role="CTRL",
            avatar_selection="canonical", role_manifest_ref=role_manifest_reference(manager),
        )
        app.progress_ledger.append(identity_manifest_event(
            other, event_id="agent-manifest-other-ctrl", dedupe_key="agent-manifest-other-ctrl-dedupe",
            observed_at_ms=50, provenance="console topology fixture",
        ))
        first = app.overview()["topology"]
        second = console.App(self.codex_home, self.config).overview()["topology"]
        self.assertEqual([root["id"] for root in first["roots"]], ["other-ctrl", "root"])
        self.assertEqual(first, second)

    def test_parent_ctrl_scope_keeps_nested_ctrl_tree_together(self) -> None:
        now = 2_000_000_000_000
        connection = sqlite3.connect(self.database)
        connection.executemany(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("child-ctrl", "🐙CTRL - Nested recovery", "C:/work/alpha", now // 1000, now, now, now,
                 "gpt-5.6-sol", "high", 40, 0, "", "main", "", "", "", 0),
                ("child-doer", "🔨DEV - Nested repair", "C:/work/alpha", now // 1000, now, now, now,
                 "gpt-5.6-luna", "high", 20, 0, "", "main", "", "", "", 0),
            ],
        )
        connection.executemany(
            "INSERT INTO thread_spawn_edges VALUES (?,?,?)",
            [("lead", "child-ctrl", "open"), ("child-ctrl", "child-doer", "open")],
        )
        connection.commit()
        connection.close()

        overview = console.build_overview(self.codex_home, self.config)
        controllers = {item["id"]: item for item in overview["controllers"]}
        by_id = {node["id"]: node for node in overview["nodes"]}
        self.assertEqual(controllers["root"]["nodes"], 5)
        self.assertEqual(controllers["child-ctrl"]["nodes"], 2)
        self.assertEqual(by_id["child-ctrl"]["controller_ids"], ["root", "child-ctrl"])
        self.assertEqual(by_id["child-doer"]["controller_ids"], ["root", "child-ctrl"])
        self.assertEqual(by_id["lead"]["controller_ids"], ["root"])
        self.assertTrue(any("not the authoritative runtime workflow graph" in claim for claim in overview["claim_limits"]))

    def test_ctrl_includes_unlabelled_host_descendants_without_exposing_prompt_title(self) -> None:
        now = 2_000_000_000_000
        connection = sqlite3.connect(self.database)
        connection.execute("ALTER TABLE threads ADD COLUMN agent_path TEXT")
        raw_title = "<codex_delegation>\nprivate task instructions\n</codex_delegation>"
        connection.execute(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("generic-child", raw_title, "C:/work/alpha", now // 1000, now // 1000, now, now,
             "gpt-5.6-terra", "high", 25, 0, "", "main", "subagent", "Lovelace", "", 0, "/root/generic_child"),
        )
        connection.execute("INSERT INTO thread_spawn_edges VALUES (?,?,?)", ("root", "generic-child", "open"))
        connection.commit()
        connection.close()

        overview = console.build_overview(self.codex_home, self.config)
        child = next(node for node in overview["nodes"] if node["id"] == "generic-child")
        self.assertEqual((child["role"], child["role_label"], child["worker_role"], child["artifact"], child["worker"]), ("doer", "TASK", "AGENT", "Generic Child", "Lovelace"))
        self.assertEqual(child["surface"], "subagent")
        self.assertTrue(child["is_subagent"])
        self.assertEqual(child["parent_id"], "root")
        self.assertEqual(child["reasoning"], "high")
        self.assertNotIn("private task instructions", json.dumps(overview))
        self.assertIn({
            "source": "root", "target": "generic-child", "relationship": "delegated", "status": "open",
        }, overview["links"])

    def test_unformatted_agent_tree_uses_project_name_without_exposing_private_titles(self) -> None:
        now = 2_000_000_000_000
        self._add_host_project("project:current", "current", "C:/work/current")
        connection = sqlite3.connect(self.database)
        connection.execute("ALTER TABLE threads ADD COLUMN agent_path TEXT")
        columns = "id,title,cwd,created_at,updated_at,created_at_ms,updated_at_ms,model,reasoning_effort,tokens_used,archived,git_origin_url,git_branch,thread_source,agent_nickname,agent_role,is_pinned,agent_path"
        connection.executemany(
            f"INSERT INTO threads ({columns}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("plain-root", "A long user request that must never render\nwith private detail", "C:/work/current", now // 1000, now // 1000, now, now, "gpt-5.6-sol", "high", 10, 0, "", "main", "", "", "", 0, ""),
                ("plain-lead", "<codex_delegation>private lead prompt</codex_delegation>", "C:/work/current", now // 1000, now // 1000, now, now, "gpt-5.6-terra", "high", 10, 0, "", "main", "subagent", "Carson", "", 0, "/root/portal_lead"),
                ("plain-lead-replacement", "<codex_delegation>replacement prompt</codex_delegation>", "C:/work/current", now // 1000, now // 1000, now, now + 1, "gpt-5.6-terra", "high", 10, 0, "", "main", "subagent", "Darwin", "", 0, "/root/portal_lead"),
                ("old-child", "<codex_delegation>old prompt</codex_delegation>", "C:/work/current", 1, 1, 1_000, 1_000, "gpt-5.6-terra", "high", 10, 0, "", "main", "subagent", "Old", "", 0, "/root/old_lane"),
            ],
        )
        connection.executemany(
            "INSERT INTO thread_spawn_edges VALUES (?,?,?)",
            [("plain-root", "plain-lead", "closed"), ("plain-root", "plain-lead-replacement", "open"), ("plain-root", "old-child", "closed")],
        )
        connection.commit()
        connection.close()

        overview = console.build_overview(self.codex_home, self.config)
        root = next(node for node in overview["nodes"] if node["id"] == "plain-root")
        lead = next(node for node in overview["nodes"] if node["id"] == "plain-lead-replacement")
        controller = next(item for item in overview["controllers"] if item["id"] == "plain-root")
        self.assertEqual((root["role_label"], root["artifact"]), ("CTRL", "current"))
        self.assertEqual((lead["role"], lead["role_label"], lead["worker_role"], lead["artifact"], lead["worker"]), ("lead", "TASK", "LEAD", "Portal", "Darwin"))
        self.assertNotIn("plain-lead", {node["id"] for node in overview["nodes"]})
        self.assertEqual(controller["older_lanes_omitted"], 1)
        self.assertNotIn("private lead prompt", json.dumps(overview))
        self.assertNotIn("old prompt", json.dumps(overview))

    def test_unformatted_fresh_spawn_tree_is_an_observed_controller_without_agent_path(self) -> None:
        now = 2_000_000_000_000
        self._add_host_project("project:nemo", "nemo", "C:/work/nemo")
        connection = sqlite3.connect(self.database)
        connection.execute("ALTER TABLE threads ADD COLUMN agent_path TEXT")
        columns = "id,title,cwd,created_at,updated_at,created_at_ms,updated_at_ms,model,reasoning_effort,tokens_used,archived,git_origin_url,git_branch,thread_source,agent_nickname,agent_role,is_pinned,agent_path"
        connection.executemany(
            f"INSERT INTO threads ({columns}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("plain-project-root", "private user objective", "C:/work/nemo", now // 1000, now // 1000, now, now, "gpt-5.6-sol", "high", 10, 0, "https://github.com/flowwweb/nemo.git", "main", "", "", "", 0, ""),
                ("plain-project-child", "<codex_delegation>private child prompt</codex_delegation>", "C:/work/nemo", now // 1000, now // 1000, now, now, "gpt-5.6-terra", "high", 5, 0, "https://github.com/flowwweb/nemo.git", "main", "subagent", "Turing", "", 0, ""),
            ],
        )
        connection.execute("INSERT INTO thread_spawn_edges VALUES (?,?,?)", ("plain-project-root", "plain-project-child", "open"))
        connection.commit()
        connection.close()

        overview = console.build_overview(self.codex_home, self.config)
        by_id = {node["id"]: node for node in overview["nodes"]}
        self.assertEqual((by_id["plain-project-root"]["role"], by_id["plain-project-root"]["artifact"]), ("ctrl", "nemo"))
        self.assertEqual((by_id["plain-project-child"]["artifact"], by_id["plain-project-child"]["worker"]), ("Assigned Task", "Turing"))
        self.assertNotIn("private user objective", json.dumps(overview))
        self.assertNotIn("private child prompt", json.dumps(overview))

    def test_extended_windows_project_path_binds_structural_host_ctrl(self) -> None:
        now = 2_000_000_000_000
        self._add_host_project(
            "project:swarm", "swarm", r"C:\Users\peikg\Documents\Codex\Projects\flowwweb\swarm",
        )
        connection = sqlite3.connect(self.database)
        connection.execute("ALTER TABLE threads ADD COLUMN project_id TEXT")
        columns = (
            "id,title,cwd,created_at,updated_at,created_at_ms,updated_at_ms,model,"
            "reasoning_effort,tokens_used,archived,git_origin_url,git_branch,thread_source,"
            "agent_nickname,agent_role,is_pinned,project_id"
        )
        connection.executemany(
            f"INSERT INTO threads ({columns}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("structural-root", "private objective", r"\\?\C:\Users\peikg\Documents\Codex\Projects\flowwweb\swarm", now // 1000, now // 1000, now, now, "gpt-5.6-sol", "high", 1, 0, "", "main", "", "", "", 0, None),
                ("structural-child", "private delegation", r"\\?\C:\Users\peikg\Documents\Codex\Projects\flowwweb\swarm", now // 1000, now // 1000, now, now, "gpt-5.6-terra", "high", 1, 0, "", "main", "subagent", "Ada", "", 0, None),
            ],
        )
        connection.execute(
            "INSERT INTO thread_spawn_edges VALUES (?,?,?)",
            ("structural-root", "structural-child", "open"),
        )
        connection.commit()
        connection.close()

        first = console.build_overview(self.codex_home, self.config)
        second = console.build_overview(self.codex_home, self.config)
        navigation = console.App._navigation_payload(first)
        controller = next(item for item in navigation["controllers"] if item["id"] == "structural-root")
        child = next(item for item in first["nodes"] if item["id"] == "structural-child")
        project = next(item for item in navigation["projects"] if item["id"] == "project:swarm")
        self.assertEqual(console._normalized_project_path(r"\\?\C:\Work\SWARM"), "c:/work/swarm")
        self.assertEqual(console._normalized_project_path(r"\\?\UNC\server\share\SWARM"), "//server/share/swarm")
        self.assertEqual(controller["controller_classification"], "swarm_ctrl")
        self.assertEqual(controller["controller_classification_source"], "host_thread_spawn_edges.subagent")
        self.assertEqual(project["ctrl_ids"], ["structural-root"])
        self.assertEqual((child["role"], child["worker_role"]), ("doer", "AGENT"))
        self.assertEqual(first["nodes"], second["nodes"])
        self.assertEqual(first["controllers"], second["controllers"])
        self.assertEqual(first["projects"], second["projects"])

        app = console.App(self.codex_home, self.config)
        with self.assertRaisesRegex(console.ConsoleError, "host-confirmed CTRL/project binding"):
            app.auto_status("structural-root", "project:swarm")
        connection = sqlite3.connect(self.database)
        connection.execute("UPDATE threads SET agent_role='ctrl' WHERE id='structural-root'")
        connection.commit()
        connection.close()
        restarted = console.App(self.codex_home, self.config)
        self.assertFalse(restarted.auto_status("structural-root", "project:swarm")["enabled"])

    def test_active_structural_ctrl_survives_stale_child_and_retains_multiple_project_ctrls(self) -> None:
        now = int(time.time() * 1000)
        self._add_host_project("project:swarm", "swarm", "C:/work/swarm")
        connection = sqlite3.connect(self.database)
        rows = [
            ("active-root-a", r"\\?\C:\work\swarm", now, "", ""),
            ("active-child-a", r"\\?\C:\work\swarm\lane-a", now - 2 * 60 * 60 * 1000, "subagent", ""),
            ("active-root-b", r"\\?\C:\work\swarm", now - 5 * 60 * 1000, "", ""),
            ("active-child-b", r"\\?\C:\work\swarm\lane-b", now - 3 * 60 * 60 * 1000, "subagent", ""),
        ]
        connection.executemany(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (thread_id, "private host task", cwd, updated // 1000, updated // 1000, updated, updated,
                 "gpt-5.6-sol", "high", 1, 0, "", "main", source, "", role, 0)
                for thread_id, cwd, updated, source, role in rows
            ],
        )
        connection.executemany(
            "INSERT INTO thread_spawn_edges VALUES (?,?,?)",
            [
                ("active-root-a", "active-child-a", "open"),
                ("active-root-b", "active-child-b", "open"),
            ],
        )
        connection.commit()
        connection.close()

        overview = console.build_overview(self.codex_home, self.config)
        navigation = console.App._navigation_payload(overview)
        controllers = {item["id"]: item for item in navigation["controllers"]}
        project = next(item for item in navigation["projects"] if item["id"] == "project:swarm")

        self.assertEqual(
            {controllers["active-root-a"]["controller_classification_source"],
             controllers["active-root-b"]["controller_classification_source"]},
            {"host_thread_spawn_edges.subagent"},
        )
        self.assertEqual(
            {controllers["active-root-a"]["activity_status"], controllers["active-root-b"]["activity_status"]},
            {"active"},
        )
        self.assertTrue(controllers["active-root-a"]["active_now"])
        self.assertTrue(controllers["active-root-b"]["active_now"])
        self.assertEqual(project["ctrl_ids"], ["active-root-a", "active-root-b"])
        self.assertEqual(project["active_ctrl_ids"], ["active-root-a", "active-root-b"])
        self.assertEqual(project["active_now_count"], 2)
        self.assertEqual(project["recently_active_count"], 0)
        self.assertEqual(project["activity_status"], "active")
        self.assertEqual(project["activity_facts"]["active_now_count"], 2)
        self.assertEqual(navigation["active_ctrl_ids"], ["active-root-a", "active-root-b"])

        app = console.App(self.codex_home, self.config)
        with self.assertRaisesRegex(console.ConsoleError, "host-confirmed CTRL/project binding"):
            app.auto_status("active-root-a", "project:swarm")

    def test_recent_activity_uses_one_day_cutoff_and_expired_edges_fail_closed(self) -> None:
        now = int(time.time() * 1000)
        self._add_host_project("project:recent", "recent", "C:/work/recent")
        self._add_host_project("project:expired", "expired", "C:/work/expired")
        connection = sqlite3.connect(self.database)
        rows = [
            ("recent-root", "C:/work/recent", now - 3 * 60 * 60 * 1000, "", ""),
            ("recent-child", "C:/work/recent/lane", now - 3 * 60 * 60 * 1000, "subagent", ""),
            ("expired-root", "C:/work/expired", now - 25 * 60 * 60 * 1000, "", ""),
            ("expired-child", "C:/work/expired/lane", now - 25 * 60 * 60 * 1000, "subagent", ""),
        ]
        connection.executemany(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (thread_id, "private host task", cwd, updated // 1000, updated // 1000, updated, updated,
                 "gpt-5.6-sol", "high", 1, 0, "", "main", source, "", role, 0)
                for thread_id, cwd, updated, source, role in rows
            ],
        )
        connection.executemany(
            "INSERT INTO thread_spawn_edges VALUES (?,?,?)",
            [
                ("recent-root", "recent-child", "open"),
                ("expired-root", "expired-child", "open"),
            ],
        )
        connection.commit()
        connection.close()

        navigation = console.App._navigation_payload(console.build_overview(self.codex_home, self.config))
        controllers = {item["id"]: item for item in navigation["controllers"]}
        recent = next(item for item in navigation["projects"] if item["id"] == "project:recent")
        expired = next(item for item in navigation["projects"] if item["id"] == "project:expired")

        self.assertEqual(controllers["recent-root"]["activity_status"], "recently_active")
        self.assertFalse(controllers["recent-root"]["active_now"])
        self.assertTrue(controllers["recent-root"]["recently_active"])
        self.assertEqual(recent["activity_status"], "recently_active")
        self.assertEqual(recent["active_now_count"], 0)
        self.assertEqual(recent["recently_active_count"], 1)
        self.assertFalse(recent["activity_facts"]["active_now"])
        self.assertTrue(recent["activity_facts"]["recently_active"])
        self.assertEqual(expired["ctrl_ids"], [])
        self.assertEqual(expired["activity_status"], "inactive")
        self.assertTrue(expired["activity_facts"]["inactive"])

    def test_structural_ctrl_requires_fresh_open_project_bound_subagent(self) -> None:
        now = 2_000_000_000_000
        old = now - 3 * 60 * 60 * 1000
        self._add_host_project("project:structural", "structural", "C:/work/structural")
        connection = sqlite3.connect(self.database)
        rows = [
            ("title-only", "🐙CTRL - Legacy title", "C:/work/structural", now, "", ""),
            ("closed-root", "private", "C:/work/structural", now, "", ""),
            ("closed-child", "private", "C:/work/structural", now, "subagent", ""),
            ("stale-root", "private", "C:/work/structural", old, "", ""),
            ("stale-child", "private", "C:/work/structural", old, "subagent", ""),
            ("ordinary-root", "private", "C:/work/structural", now, "", ""),
            ("ordinary-child", "private", "C:/work/structural", now, "agent", ""),
            ("unbound-root", "private", "C:/other/unbound", now, "", ""),
            ("unbound-child", "private", "C:/other/unbound", now, "subagent", ""),
        ]
        connection.executemany(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (thread_id, title, cwd, updated // 1000, updated // 1000, updated, updated, "gpt-5.6-sol", "high", 1, 0, "", "main", source, "", role, 0)
                for thread_id, title, cwd, updated, source, role in rows
            ],
        )
        connection.executemany(
            "INSERT INTO thread_spawn_edges VALUES (?,?,?)",
            [
                ("closed-root", "closed-child", "closed"),
                ("stale-root", "stale-child", "open"),
                ("ordinary-root", "ordinary-child", "open"),
                ("unbound-root", "unbound-child", "open"),
            ],
        )
        connection.commit()
        connection.close()

        navigation = console.App._navigation_payload(console.build_overview(self.codex_home, self.config))
        controllers = {item["id"]: item for item in navigation["controllers"]}
        for controller_id in ("title-only", "closed-root", "ordinary-root", "unbound-root"):
            if controller_id in controllers:
                self.assertEqual(controllers[controller_id]["controller_classification"], "unavailable")
        project = next(item for item in navigation["projects"] if item["id"] == "project:structural")
        self.assertNotIn("title-only", project["ctrl_ids"])
        self.assertNotIn("closed-root", project["ctrl_ids"])
        self.assertNotIn("ordinary-root", project["ctrl_ids"])

    def test_structural_ctrl_rejects_conflicting_parentage_and_subagent_roots(self) -> None:
        now = 2_000_000_000_000
        self._add_host_project("project:conflict", "conflict", "C:/work/conflict")
        connection = sqlite3.connect(self.database)
        rows = [
            ("root-a", "private", "", ""),
            ("root-b", "private", "", ""),
            ("shared-child", "private", "subagent", ""),
            ("status-root", "private", "", ""),
            ("status-child", "private", "subagent", ""),
            ("nested-parent", "private", "subagent", ""),
            ("nested-child", "private", "subagent", ""),
        ]
        connection.executemany(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (thread_id, title, "C:/work/conflict", now // 1000, now // 1000, now, now, "gpt-5.6-sol", "high", 1, 0, "", "main", source, "", role, 0)
                for thread_id, title, source, role in rows
            ],
        )
        connection.executemany(
            "INSERT INTO thread_spawn_edges VALUES (?,?,?)",
            [
                ("root-a", "shared-child", "open"),
                ("root-b", "shared-child", "open"),
                ("status-root", "status-child", "open"),
                ("status-root", "status-child", "closed"),
                ("nested-parent", "nested-child", "open"),
            ],
        )
        connection.commit()
        connection.close()

        navigation = console.App._navigation_payload(console.build_overview(self.codex_home, self.config))
        controllers = {item["id"]: item for item in navigation["controllers"]}
        for controller_id in ("root-a", "root-b", "status-root", "nested-parent"):
            if controller_id in controllers:
                self.assertEqual(controllers[controller_id]["controller_classification"], "unavailable")
        project = next(item for item in navigation["projects"] if item["id"] == "project:conflict")
        self.assertEqual(project["ctrl_ids"], [])

    def test_structural_ctrl_rejects_ambiguous_incoming_edge_even_with_valid_child(self) -> None:
        now = 2_000_000_000_000
        self._add_host_project("project:incoming", "incoming", "C:/work/incoming")
        connection = sqlite3.connect(self.database)
        rows = [
            ("parent-a", "", ""),
            ("parent-b", "", ""),
            ("ambiguous-root", "", ""),
            ("genuine-child", "subagent", ""),
        ]
        connection.executemany(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (thread_id, "private", "C:/work/incoming", now // 1000, now // 1000, now, now, "gpt-5.6-sol", "high", 1, 0, "", "main", source, "", role, 0)
                for thread_id, source, role in rows
            ],
        )
        connection.executemany(
            "INSERT INTO thread_spawn_edges VALUES (?,?,?)",
            [
                ("parent-a", "ambiguous-root", "open"),
                ("parent-b", "ambiguous-root", "open"),
                ("ambiguous-root", "genuine-child", "open"),
            ],
        )
        connection.commit()
        connection.close()

        navigation = console.App._navigation_payload(console.build_overview(self.codex_home, self.config))
        controllers = {item["id"]: item for item in navigation["controllers"]}
        if "ambiguous-root" in controllers:
            self.assertEqual(controllers["ambiguous-root"]["controller_classification"], "unavailable")
        project = next(item for item in navigation["projects"] if item["id"] == "project:incoming")
        self.assertNotIn("ambiguous-root", project["ctrl_ids"])
        self.assertEqual(project["activity_status"], "active")
        self.assertTrue(project["activity_facts"]["active_now"])
        self.assertFalse(project["activity_facts"]["unknown"])
        self.assertEqual(
            set(project["activity_facts"]["unknown_controller_ids"]),
            {"parent-a", "parent-b"},
        )
        self.assertIn("unambiguous structural classification", project["activity_facts"]["unknown_reason"])

    def test_projects_require_canonical_host_identity_and_preserve_unbound_tasks(self) -> None:
        now = 2_000_000_000_000
        self._add_host_project("project:real-hyphen", "real-project-with-hyphens", "C:/saved/real-project")
        self._add_host_project("project:competing", "competing-project", "C:/ambiguous")
        connection = sqlite3.connect(self.database)
        connection.execute("ALTER TABLE threads ADD COLUMN project_id TEXT")
        connection.execute(
            "INSERT INTO project_roots VALUES (?,?,?)",
            ("project:real-hyphen", 1, "C:/ambiguous"),
        )
        columns = (
            "id,title,cwd,created_at,updated_at,created_at_ms,updated_at_ms,model,"
            "reasoning_effort,tokens_used,archived,git_origin_url,git_branch,thread_source,"
            "agent_nickname,agent_role,is_pinned,project_id"
        )
        rows = [
            ("real-ctrl", "🐙CTRL - Real delivery", "C:/unrelated/worktree", "project:real-hyphen", "ctrl", ""),
            ("real-task", "🔨DEV - Bound implementation", "C:/unrelated/task", None, "", "subagent"),
            ("delegation-label", "🐙CTRL - codex-delegation-source-thread-id-123", "C:/work/codex-delegation-source-thread-id-123", None, "ctrl", ""),
            ("runtime-cleanup", "🐙CTRL - helm-682-runtime-cache-cleanup", "C:/work/helm-682-runtime-cache-cleanup", None, "ctrl", ""),
            ("architecture-lead", "🧭LEAD - helm-ai-v1-architecture-lead", "C:/work/helm-ai-v1-architecture-lead", None, "", "subagent"),
            ("ctrl-label", "🐙CTRL - helm-ai-v1-ctrl-2026-08-26", "C:/work/helm-ai-v1-ctrl-2026-08-26", None, "ctrl", ""),
            ("stale-project", "🐙CTRL - Stale binding", "C:/saved/real-project", "project:missing", "ctrl", ""),
            ("ambiguous-child", "🔨DEV - Ambiguous binding", "C:/ambiguous/task", None, "", "subagent"),
        ]
        connection.executemany(
            f"INSERT INTO threads ({columns}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (thread_id, title, cwd, now // 1000, now // 1000, now, now, "gpt-5.6-sol", "high", 1, 0,
                 "https://github.com/flowwweb/fake-label.git", "main", thread_source, "", agent_role, 0, project_id)
                for thread_id, title, cwd, project_id, agent_role, thread_source in rows
            ],
        )
        connection.executemany(
            "INSERT INTO thread_spawn_edges VALUES (?,?,?)",
            [
                ("real-ctrl", "real-task", "open"),
                ("real-ctrl", "ambiguous-child", "open"),
                ("delegation-label", "architecture-lead", "open"),
            ],
        )
        connection.commit()
        connection.close()

        overview = console.build_overview(self.codex_home, self.config)
        navigation = console.App._navigation_payload(overview)
        project_names = {project["name"] for project in overview["projects"]}
        navigation_names = {project["name"] for project in navigation["projects"]}
        nodes = {node["id"]: node for node in overview["nodes"]}

        self.assertEqual(project_names, {"alpha", "competing-project", "real-project-with-hyphens"})
        self.assertEqual(navigation_names, project_names)
        self.assertEqual(nodes["real-ctrl"]["project_id"], "project:real-hyphen")
        self.assertEqual(nodes["real-task"]["project_id"], "project:real-hyphen")
        self.assertEqual(nodes["stale-project"]["project_id"], "")
        self.assertEqual(nodes["ambiguous-child"]["project_id"], "")
        for thread_id in ("delegation-label", "runtime-cleanup", "architecture-lead", "ctrl-label"):
            self.assertIn(thread_id, nodes)
            self.assertEqual(nodes[thread_id]["project_id"], "")
        serialized_projects = json.dumps(overview["projects"])
        for label in (
            "codex-delegation-source-thread-id",
            "helm-682-runtime-cache-cleanup",
            "helm-ai-v1-architecture-lead",
            "helm-ai-v1-ctrl-2026-08-26",
            "fake-label",
        ):
            self.assertNotIn(label, serialized_projects)
        self.assertEqual(console.observed_task_project_id(self.codex_home, "real-task"), "project:real-hyphen")
        self.assertIsNone(console.observed_task_project_id(self.codex_home, "stale-project"))
        self.assertIsNone(console.observed_task_project_id(self.codex_home, "ambiguous-child"))

    def _handler(self, peer: str, host: str, *, origin: str = "", token: str = "secret"):
        handler = object.__new__(console.Handler)
        handler.client_address = (peer, 41000)
        handler.headers = Message()
        handler.headers["Host"] = host
        if origin:
            handler.headers["Origin"] = origin
        if token:
            handler.headers["X-Swarm-Token"] = token
        handler.server = SimpleNamespace(app=SimpleNamespace(token="secret", config_path=self.config))
        return handler

    def _storage_handler(self, *, result: dict | None = None, error: Exception | None = None):
        handler = self._handler("127.0.0.1", "127.0.0.1:4788")
        handler.path = "/api/storage"
        handler.server.app.storage = mock.Mock(return_value={} if result is None else result, side_effect=error)
        handler.send_response = mock.Mock(side_effect=lambda *_args, **_kwargs: setattr(handler, "_response_committed", False))
        handler.send_header = mock.Mock()
        handler.end_headers = mock.Mock(side_effect=lambda: setattr(handler, "_response_committed", True))
        handler.wfile = SimpleNamespace(write=mock.Mock())
        return handler

    def test_precommit_storage_failures_emit_one_structured_500(self) -> None:
        for error in (OSError("storage unavailable"), sqlite3.OperationalError("database busy")):
            with self.subTest(error=type(error).__name__):
                handler = self._storage_handler(error=error)
                handler._response_committed = True
                handler._json = mock.Mock()

                handler.do_GET()

                handler._json.assert_called_once_with(
                    console.HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"ok": False, "error": str(error)},
                )

    def test_postcommit_client_disconnects_do_not_emit_second_response(self) -> None:
        errors: list[OSError] = [
            BrokenPipeError("client closed"),
            ConnectionResetError("client reset"),
            ConnectionAbortedError("client aborted"),
        ]
        for winerror in (10053, 10054):
            error = OSError("windows client disconnected")
            error.winerror = winerror
            errors.append(error)

        for error in errors:
            for phase in ("headers", "body"):
                with self.subTest(error=type(error).__name__, winerror=getattr(error, "winerror", None), phase=phase):
                    handler = self._storage_handler()
                    if phase == "headers":
                        def disconnect_during_headers() -> None:
                            handler._response_committed = True
                            raise error

                        handler.end_headers.side_effect = disconnect_during_headers
                    else:
                        handler.wfile.write.side_effect = error

                    handler.do_GET()

                    self.assertEqual(handler.send_response.call_count, 1)
                    self.assertEqual(handler.wfile.write.call_count, int(phase == "body"))

    def test_response_boundary_tracks_each_request_commit(self) -> None:
        handler = self._handler("127.0.0.1", "127.0.0.1:4788")
        with mock.patch.object(console.BaseHTTPRequestHandler, "send_response") as send_response:
            handler._response_committed = True
            handler.send_response(console.HTTPStatus.OK)
            self.assertFalse(handler._response_committed)
            send_response.assert_called_once_with(console.HTTPStatus.OK, None)
        with mock.patch.object(console.BaseHTTPRequestHandler, "end_headers") as end_headers:
            handler.end_headers()
            self.assertTrue(handler._response_committed)
            end_headers.assert_called_once_with()

    def test_unknown_postcommit_io_failure_never_attempts_second_response(self) -> None:
        handler = self._storage_handler()
        handler.wfile.write.side_effect = OSError("unexpected response write failure")

        with self.assertRaisesRegex(OSError, "unexpected response write failure"):
            handler.do_GET()

        self.assertEqual(handler.send_response.call_count, 1)

    def test_console_server_handler_has_exact_plugin_mirror(self) -> None:
        plugin_server = SERVER.parents[1] / "plugins" / "swarm" / "console" / "server.py"
        self.assertEqual(SERVER.read_bytes(), plugin_server.read_bytes())

    def test_remote_peer_cannot_acquire_token_or_write_through_localhost_host(self) -> None:
        handler = self._handler("192.0.2.44", "localhost", token="secret")
        self.assertTrue(handler._host_allowed())
        self.assertFalse(handler._peer_is_loopback())
        self.assertFalse(handler._authorized_write())
        self.assertEqual(handler._bootstrap_payload()["token"], "")
        self.assertEqual(handler._bootstrap_payload()["config_path"], "")
        self.assertTrue(handler._bootstrap_payload()["read_only"])
        self.assertTrue(handler._config_payload()["read_only"])
        self.assertEqual(handler._config_payload()["path"], "")

    def test_write_requires_loopback_peer_allowed_host_origin_and_token(self) -> None:
        self.assertFalse(self._handler("127.0.0.1", "evil.example")._host_allowed())
        self.assertFalse(self._handler("127.0.0.1", "localhost", origin="http://evil.example")._authorized_write())
        self.assertFalse(self._handler("127.0.0.1", "localhost:4788", origin="http://localhost:9999")._authorized_write())
        self.assertFalse(self._handler("127.0.0.1", "localhost", token="wrong")._authorized_write())
        self.assertTrue(self._handler("127.0.0.1", "localhost")._authorized_write())
        self.assertTrue(self._handler("127.0.0.1", "localhost:4788", origin="http://localhost:4788")._authorized_write())
        self.assertTrue(self._handler("127.0.0.1", "192.168.1.10")._host_allowed())

    def test_docker_bridge_peer_is_local_only_when_explicitly_enabled(self) -> None:
        handler = self._handler("172.18.0.1", "127.0.0.1:4788", origin="http://127.0.0.1:4788")
        self.assertFalse(handler._peer_is_trusted_local())
        with mock.patch.dict(console.os.environ, {"SWARM_CONSOLE_DOCKER_LOOPBACK": "1"}):
            self.assertTrue(handler._peer_is_trusted_local())
            self.assertTrue(handler._authorized_write())
            self.assertFalse(handler._bootstrap_payload()["read_only"])

    def test_portal_open_claim_uses_visible_presence_and_bounded_ttl(self) -> None:
        app = console.App(self.codex_home, self.config)
        with mock.patch.object(console.time, "monotonic", return_value=10.0):
            self.assertTrue(app.claim_portal_open()["should_open"])
        with mock.patch.object(console.time, "monotonic", return_value=20.0):
            self.assertEqual(app.claim_portal_open()["reason"], "recent_claim")
            app.mark_presence()
        with mock.patch.object(console.time, "monotonic", return_value=80.0):
            app.mark_presence()
        with mock.patch.object(console.time, "monotonic", return_value=100.0):
            self.assertEqual(app.claim_portal_open()["reason"], "active_tab")
        with mock.patch.object(console.time, "monotonic", return_value=231.0):
            self.assertTrue(app.claim_portal_open()["should_open"])

    def test_portal_open_claim_is_once_per_observed_task_across_restart(self) -> None:
        app = console.App(self.codex_home, self.config)
        app.mark_presence()
        self.assertTrue(app.claim_portal_open("root")["should_open"])
        self.assertFalse(app.claim_portal_open("root")["should_open"])
        self.assertTrue(app.claim_portal_open("lead")["should_open"])
        restarted = console.App(self.codex_home, self.config)
        self.assertEqual(restarted.claim_portal_open("root")["reason"], "task_already_claimed")
        with self.assertRaises(console.ConsoleError):
            restarted.claim_portal_open("missing")
        with self.assertRaises(console.ConsoleError):
            restarted.claim_portal_open("bad/id")

    def test_hidden_tab_presence_is_cheap_authenticated_and_stops_on_close(self) -> None:
        app = (console.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('document.visibilityState === "hidden"', app)
        self.assertIn('api("/api/presence", { method: "POST" })', app)
        self.assertIn("proof_sequence", app)
        self.assertIn("60_000", app)
        self.assertLess(len(json.dumps({"ok": True, "proof_sequence": 0}, separators=(",", ":")).encode()), 48)

    def test_overview_cache_rebuilds_when_the_observer_reports_a_host_change(self) -> None:
        app = console.App(self.codex_home, self.config)
        first = app.overview()
        self.assertIs(first, app.overview())
        self.config.write_text(self.config.read_text(encoding="utf-8") + "\n# updated\n", encoding="utf-8")
        with mock.patch.object(app.auto_bridge, "read_account_limits", return_value={"status": "UNKNOWN", "windows": []}):
            app.observe_once("state_change")
        self.assertIsNot(first, app.overview())

    def test_overview_refresh_and_reader_do_not_invert_locks(self) -> None:
        app = console.App(self.codex_home, self.config)
        refresh_entered = threading.Event()
        release_refresh = threading.Event()
        original_fingerprint = console.observation_fingerprint
        original_build = console.build_overview
        calls = 0
        errors: list[BaseException] = []
        results: list[dict[str, object]] = []

        def delayed_fingerprint(*args: object, **kwargs: object) -> tuple[tuple[str, int, int], ...]:
            nonlocal calls
            calls += 1
            if calls == 1:
                refresh_entered.set()
                release_refresh.wait(2)
            return (("state", 1, 1),)

        def invoke_refresh() -> None:
            try:
                app._host_overview(refresh=True)
            except BaseException as error:  # pragma: no cover - reported by the assertion
                errors.append(error)

        def invoke_reader() -> None:
            try:
                results.append(app.overview())
            except BaseException as error:  # pragma: no cover - reported by the assertion
                errors.append(error)

        console.observation_fingerprint = delayed_fingerprint
        console.build_overview = lambda *_args, **_kwargs: {
            "generated_at": "2026-08-24T00:00:00+00:00",
            "heartbeat_minutes": 30,
            "nodes": [],
            "links": [],
            "projects": [],
            "controllers": [],
            "analytics": {},
        }
        try:
            refresh = threading.Thread(target=invoke_refresh, daemon=True)
            refresh.start()
            self.assertTrue(refresh_entered.wait(1), "refresh did not reach the lock boundary")
            reader = threading.Thread(target=invoke_reader, daemon=True)
            reader.start()
            release_refresh.set()
            refresh.join(2)
            reader.join(2)
            self.assertFalse(refresh.is_alive(), "overview refresh remained deadlocked")
            self.assertFalse(reader.is_alive(), "overview reader remained deadlocked")
            self.assertEqual(errors, [])
            self.assertEqual(len(results), 1)
        finally:
            release_refresh.set()
            console.observation_fingerprint = original_fingerprint
            console.build_overview = original_build

    def test_jsonl_scan_is_shared_and_does_not_hold_console_store_lock(self) -> None:
        store = console.ConsoleStore(self.root / "console" / "console-state.sqlite3")
        scan_entered = threading.Event()
        release_scan = threading.Event()
        original_scan = console._codex_jsonl_token_counts
        errors: list[BaseException] = []
        scanned_ids: list[set[str]] = []
        overview = {
            "heartbeat_minutes": 30,
            "nodes": [
                {"id": "thread-1", "project_id": "project:alpha", "tokens": 10, "status": "active", "updated_at": 1_000},
                {"id": "thread-2", "project_id": "project:alpha", "tokens": 20, "status": "active", "updated_at": 1_000},
            ],
            "links": [],
        }

        def delayed_scan(_codex_home: Path, thread_ids: set[str]) -> dict[str, int]:
            scanned_ids.append(set(thread_ids))
            scan_entered.set()
            release_scan.wait(2)
            return {}

        def observe() -> None:
            try:
                store.observe_overview(overview, codex_home=self.codex_home, now_ms=1_000, trigger="heartbeat", heartbeat_minutes=30)
            except BaseException as error:  # pragma: no cover - reported by the assertion
                errors.append(error)

        console._codex_jsonl_token_counts = delayed_scan
        try:
            worker = threading.Thread(target=observe, daemon=True)
            worker.start()
            self.assertTrue(scan_entered.wait(1), "observer did not reach the JSONL scan")
            started = time.monotonic()
            self.assertEqual(store.token_history(hours=24), [])
            self.assertLess(time.monotonic() - started, 0.5)
            release_scan.set()
            worker.join(2)
            self.assertFalse(worker.is_alive(), "observer did not complete after scan release")
            self.assertEqual(errors, [])
            self.assertEqual(scanned_ids, [{"thread-1", "thread-2"}])
        finally:
            release_scan.set()
            console._codex_jsonl_token_counts = original_scan

    def test_recent_active_goal_identifies_ctrl_without_reading_objective_text(self) -> None:
        goals = sqlite3.connect(self.codex_home / "goals_1.sqlite")
        goals.execute(
            "CREATE TABLE thread_goals (thread_id TEXT PRIMARY KEY, goal_id TEXT, objective TEXT, status TEXT, token_budget INTEGER, tokens_used INTEGER, time_used_seconds INTEGER, created_at_ms INTEGER, updated_at_ms INTEGER)"
        )
        goals.execute(
            "INSERT INTO thread_goals VALUES (?,?,?,?,?,?,?,?,?)",
            ("unsafe", "goal-1", "private objective must never render", "active", None, 0, 0, 2_000_000_000_000, 2_000_000_000_000),
        )
        goals.commit()
        goals.close()

        overview = console.build_overview(self.codex_home, self.config)
        node = next(node for node in overview["nodes"] if node["id"] == "unsafe")
        self.assertEqual((node["role"], node["artifact"], node["project_id"]), ("ctrl", "Unbound work", ""))
        self.assertNotIn("private objective", json.dumps(overview))

    def test_goal_database_change_invalidates_cached_overview(self) -> None:
        goals = sqlite3.connect(self.codex_home / "goals_1.sqlite")
        goals.execute(
            "CREATE TABLE thread_goals (thread_id TEXT PRIMARY KEY, goal_id TEXT, objective TEXT, status TEXT, token_budget INTEGER, tokens_used INTEGER, time_used_seconds INTEGER, created_at_ms INTEGER, updated_at_ms INTEGER)"
        )
        goals.commit()
        goals.close()
        app = console.App(self.codex_home, self.config)
        first = app.overview()
        goals = sqlite3.connect(self.codex_home / "goals_1.sqlite")
        goals.execute(
            "INSERT INTO thread_goals VALUES (?,?,?,?,?,?,?,?,?)",
            ("unsafe", "goal-2", "private", "active", None, 0, 0, 2_000_000_000_000, 2_000_000_000_000),
        )
        goals.commit()
        goals.close()
        with mock.patch.object(app.auto_bridge, "read_account_limits", return_value={"status": "UNKNOWN", "windows": []}):
            app.observe_once("state_change")
        self.assertIsNot(first, app.overview())

    def test_console_store_survives_restart_and_clamps_counter_resets(self) -> None:
        path = self.root / "console" / "console-state.sqlite3"
        now = int(time.time() * 1000)
        overview = {
            "heartbeat_minutes": 30,
            "nodes": [{
                "id": "thread-1", "project_id": "project:alpha", "tokens": 100,
                "status": "active", "updated_at": now,
            }],
            "links": [],
        }
        store = console.ConsoleStore(path)
        store.observe_overview(overview, now_ms=now, trigger="startup", heartbeat_minutes=30)
        overview["nodes"][0]["tokens"] = 100
        store.observe_overview(overview, now_ms=now + 61_000, trigger="heartbeat", heartbeat_minutes=30)
        overview["nodes"][0]["tokens"] = 90
        store.observe_overview(overview, now_ms=now + 122_000, trigger="heartbeat", heartbeat_minutes=30)
        store.observe_overview(overview, now_ms=now + 183_000, trigger="heartbeat", heartbeat_minutes=30)
        overview["nodes"][0]["tokens"] = 130
        store.observe_overview(overview, now_ms=now + 244_000, trigger="state_change", heartbeat_minutes=30)
        restarted = console.ConsoleStore(path)
        history = restarted.token_history(hours=24, before_ms=now + 244_000)
        self.assertEqual(sum(item["delta_tokens"] for item in history), 30)
        samples = restarted.token_sample_series(
            project_id="project:alpha", thread_ids={"thread-1"}, hours=24, before_ms=now + 244_000,
        )
        self.assertEqual(sum(item["tokens"] for item in samples), 30)
        self.assertEqual({item["task_id"] for item in samples}, {"thread-1"})
        self.assertEqual(
            restarted.token_sample_series(project_id="project:alpha", thread_ids=set(), hours=24),
            [],
        )
        self.assertEqual(restarted.storage_stats()["counts"]["token_samples"], 5)
        connection = sqlite3.connect(path)
        try:
            cursor = connection.execute(
                "SELECT cumulative_tokens FROM token_cursors WHERE thread_id='thread-1'"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(cursor[0], 130)

    def test_execution_queue_persists_reservation_generation_and_event_dedupe_across_restart(self) -> None:
        path = self.root / "console" / "execution-state.sqlite3"
        ledger = console.ExecutionDispatchLedger()
        ledger.observe_generation(console.ExecutionConfigGeneration("generation-fast", True, "gpt-5.6", "high", 10, "host:config:fast"))
        ledger.reserve("reservation-1", "task-1", "owner-1", ArtifactIdentity("artifact", "rev-1", "queue"), observed_at_ms=11)
        record = ledger.dispatch("reservation-1", "a" * 64, 900, observed_at_ms=12)
        event = CodexAppServerAdapter().translate_event({
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "turnId": "turn-1", "status": "completed"},
        })
        self.assertTrue(ledger.observe_event("reservation-1", event, observed_at_ms=13))
        store = console.ConsoleStore(path)
        store.persist_execution_ledger(ledger, now_ms=14)
        with self.assertRaisesRegex(console.ConsoleError, "typed state"):
            store.persist_execution_ledger({"prompt": "private"}, now_ms=14)
        with closing(sqlite3.connect(path)) as connection:
            retained = connection.execute("SELECT snapshot_json FROM execution_dispatch_state").fetchone()[0]
        self.assertNotIn("prompt", retained.casefold())
        self.assertNotIn("private", retained.casefold())

        restarted = console.ConsoleStore(path).load_execution_ledger()
        restored = restarted.reservation("reservation-1")
        self.assertEqual((restored.state, restored.host_completed, restored.requested_service_tier), (ExecutionDispatchState.ACTIVE, True, "fast"))
        self.assertFalse(restarted.observe_event("reservation-1", event, observed_at_ms=15))
        with self.assertRaisesRegex(InvariantError, "duplicate dispatch"):
            restarted.dispatch("reservation-1", "c" * 64, 800, observed_at_ms=16)

        restarted.observe_generation(console.ExecutionConfigGeneration("generation-standard", False, "gpt-5.6", "high", 20, "host:config:standard"))
        restarted.checkpoint("reservation-1", observed_at_ms=21)
        resumed = restarted.dispatch("reservation-1", "d" * 64, 700, observed_at_ms=22)
        self.assertEqual((resumed.generation_id, resumed.requested_service_tier), ("generation-standard", "default"))
        store.persist_execution_ledger(restarted, now_ms=23)
        final = console.ConsoleStore(path).load_execution_ledger().reservation("reservation-1")
        self.assertEqual((final.generation_id, final.requested_service_tier, final.service_tier_truth.value), ("generation-standard", "default", "unverified"))

    def test_execution_reservation_persistence_rejects_stale_and_conflicting_snapshots(self) -> None:
        path = self.root / "console" / "execution-cas.sqlite3"
        store = console.ConsoleStore(path)
        ledger = console.ExecutionDispatchLedger()
        ledger.observe_generation(console.ExecutionConfigGeneration("generation-fast", True, "gpt-5.6", "high", 10, "host:config:fast"))
        ledger.reserve("reservation-cas", "task-cas", "owner-cas", ArtifactIdentity("artifact", "rev-cas", "queue"), observed_at_ms=11)
        active = ledger.dispatch("reservation-cas", "a" * 64, 900, observed_at_ms=12)
        stale_before_completion = copy.deepcopy(active.snapshot())
        store.persist_execution_ledger(ledger, now_ms=12)
        store.persist_execution_ledger(ledger, now_ms=12)  # exact digest replay is idempotent

        event = CodexAppServerAdapter().translate_event({
            "method": "turn/completed",
            "params": {"threadId": "thread-cas", "turnId": "turn-cas", "status": "completed"},
        })
        self.assertTrue(ledger.observe_event("reservation-cas", event, observed_at_ms=13))
        completed_snapshot = copy.deepcopy(active.snapshot())
        store.persist_execution_ledger(ledger, now_ms=13)

        stale_ledger = console.ExecutionDispatchLedger(
            generations=ledger.generations,
            reservations=(console.ExecutionReservation.from_snapshot(stale_before_completion),),
        )
        with self.assertRaisesRegex(console.ConsoleError, "stale execution reservation"):
            store.persist_execution_ledger(stale_ledger, now_ms=14)

        equal_time_conflict = copy.deepcopy(completed_snapshot)
        equal_time_conflict["host_turn_id"] = "turn-conflict"
        conflicting_ledger = console.ExecutionDispatchLedger(
            generations=ledger.generations,
            reservations=(console.ExecutionReservation.from_snapshot(equal_time_conflict),),
        )
        with self.assertRaisesRegex(console.ConsoleError, "equal-time execution reservation"):
            store.persist_execution_ledger(conflicting_ledger, now_ms=14)

        forward_snapshots = []
        for state, observed_at_ms in (
            (ExecutionDispatchState.MATERIAL_RECEIPT, 14),
            (ExecutionDispatchState.INDEPENDENT_REVIEW, 15),
            (ExecutionDispatchState.COMPLETE, 16),
        ):
            snapshot = copy.deepcopy(completed_snapshot)
            snapshot["state"] = state.value
            snapshot["material_receipt_id"] = "receipt-cas"
            snapshot["updated_at_ms"] = observed_at_ms
            forward_snapshots.append(snapshot)
            store.persist_execution_ledger(
                console.ExecutionDispatchLedger(
                    generations=ledger.generations,
                    reservations=(console.ExecutionReservation.from_snapshot(snapshot),),
                ),
                now_ms=observed_at_ms,
            )

        stale_after_completion = console.ExecutionDispatchLedger(
            generations=ledger.generations,
            reservations=(console.ExecutionReservation.from_snapshot(forward_snapshots[0]),),
        )
        with self.assertRaisesRegex(console.ConsoleError, "stale execution reservation"):
            store.persist_execution_ledger(stale_after_completion, now_ms=17)
        retained = store.load_execution_ledger().reservation("reservation-cas")
        self.assertEqual((retained.state, retained.host_completed, retained.material_receipt_id), (ExecutionDispatchState.COMPLETE, True, "receipt-cas"))

    def test_execution_completion_requires_retained_independent_review(self) -> None:
        path = self.root / "console" / "execution-review-cas.sqlite3"
        store = console.ConsoleStore(path)
        ledger = console.ExecutionDispatchLedger()
        ledger.observe_generation(console.ExecutionConfigGeneration("generation-fast", True, "gpt-5.6", "high", 10, "host:config:fast"))
        ledger.reserve("reservation-review", "task-review", "owner-review", ArtifactIdentity("artifact", "rev-review", "queue"), observed_at_ms=11)
        active = ledger.dispatch("reservation-review", "f" * 64, 700, observed_at_ms=12)
        event = CodexAppServerAdapter().translate_event({
            "method": "turn/completed",
            "params": {"threadId": "thread-review", "turnId": "turn-review", "status": "completed"},
        })
        ledger.observe_event("reservation-review", event, observed_at_ms=13)
        active_snapshot = copy.deepcopy(active.snapshot())
        store.persist_execution_ledger(ledger, now_ms=13)

        def snapshot_ledger(snapshot: dict[str, object]) -> object:
            return console.ExecutionDispatchLedger(
                generations=ledger.generations,
                reservations=(console.ExecutionReservation.from_snapshot(snapshot),),
            )

        fabricated_review = copy.deepcopy(active_snapshot)
        fabricated_review.update(state=ExecutionDispatchState.INDEPENDENT_REVIEW.value, material_receipt_id="fabricated-review", updated_at_ms=14)
        with self.assertRaisesRegex(console.ConsoleError, "requires a retained exact material receipt"):
            store.persist_execution_ledger(snapshot_ledger(fabricated_review), now_ms=14)

        direct_complete = copy.deepcopy(active_snapshot)
        direct_complete.update(state=ExecutionDispatchState.COMPLETE.value, material_receipt_id="receipt-review", updated_at_ms=14)
        with self.assertRaisesRegex(console.ConsoleError, "requires retained independent review"):
            store.persist_execution_ledger(snapshot_ledger(direct_complete), now_ms=14)

        checkpointed = copy.deepcopy(active_snapshot)
        checkpointed.update(state=ExecutionDispatchState.CHECKPOINTED.value, updated_at_ms=14)
        store.persist_execution_ledger(snapshot_ledger(checkpointed), now_ms=14)
        checkpoint_review = copy.deepcopy(fabricated_review)
        checkpoint_review["updated_at_ms"] = 15
        with self.assertRaisesRegex(console.ConsoleError, "requires a retained exact material receipt"):
            store.persist_execution_ledger(snapshot_ledger(checkpoint_review), now_ms=15)
        checkpoint_complete = copy.deepcopy(direct_complete)
        checkpoint_complete["updated_at_ms"] = 15
        with self.assertRaisesRegex(console.ConsoleError, "requires retained independent review"):
            store.persist_execution_ledger(snapshot_ledger(checkpoint_complete), now_ms=15)

        rejected_review = copy.deepcopy(active_snapshot)
        rejected_review.update(state=ExecutionDispatchState.UNVERIFIED.value, updated_at_ms=15)
        store.persist_execution_ledger(snapshot_ledger(rejected_review), now_ms=15)
        unverified_review = copy.deepcopy(fabricated_review)
        unverified_review["updated_at_ms"] = 16
        with self.assertRaisesRegex(console.ConsoleError, "requires a retained exact material receipt"):
            store.persist_execution_ledger(snapshot_ledger(unverified_review), now_ms=16)
        rejected_complete = copy.deepcopy(direct_complete)
        rejected_complete["updated_at_ms"] = 16
        with self.assertRaisesRegex(console.ConsoleError, "requires retained independent review"):
            store.persist_execution_ledger(snapshot_ledger(rejected_complete), now_ms=16)

        material = copy.deepcopy(active_snapshot)
        material.update(state=ExecutionDispatchState.MATERIAL_RECEIPT.value, material_receipt_id="receipt-review", updated_at_ms=16)
        store.persist_execution_ledger(snapshot_ledger(material), now_ms=16)
        mismatched_receipt = copy.deepcopy(material)
        mismatched_receipt.update(state=ExecutionDispatchState.INDEPENDENT_REVIEW.value, material_receipt_id="other-receipt", updated_at_ms=17)
        with self.assertRaisesRegex(console.ConsoleError, "cannot replace retained material receipt"):
            store.persist_execution_ledger(snapshot_ledger(mismatched_receipt), now_ms=17)
        mismatched_generation = copy.deepcopy(material)
        mismatched_generation.update(state=ExecutionDispatchState.INDEPENDENT_REVIEW.value, generation_id="other-generation", updated_at_ms=17)
        with self.assertRaisesRegex(console.ConsoleError, "conflicts with retained material receipt binding"):
            store.persist_execution_ledger(snapshot_ledger(mismatched_generation), now_ms=17)
        mismatched_review = copy.deepcopy(material)
        mismatched_review["state"] = ExecutionDispatchState.INDEPENDENT_REVIEW.value
        mismatched_review["artifact"] = dict(mismatched_review["artifact"], revision="wrong-revision")
        mismatched_review["updated_at_ms"] = 17
        with self.assertRaisesRegex(console.ConsoleError, "conflicts with retained identity"):
            store.persist_execution_ledger(snapshot_ledger(mismatched_review), now_ms=17)
        stale_review = copy.deepcopy(material)
        stale_review.update(state=ExecutionDispatchState.INDEPENDENT_REVIEW.value, updated_at_ms=15)
        with self.assertRaisesRegex(console.ConsoleError, "stale execution reservation"):
            store.persist_execution_ledger(snapshot_ledger(stale_review), now_ms=17)

        accepted_review = copy.deepcopy(material)
        accepted_review.update(state=ExecutionDispatchState.INDEPENDENT_REVIEW.value, updated_at_ms=17)
        store.persist_execution_ledger(snapshot_ledger(accepted_review), now_ms=17)
        accepted_complete = copy.deepcopy(accepted_review)
        accepted_complete.update(state=ExecutionDispatchState.COMPLETE.value, updated_at_ms=18)
        complete_ledger = snapshot_ledger(accepted_complete)
        store.persist_execution_ledger(complete_ledger, now_ms=18)
        store.persist_execution_ledger(complete_ledger, now_ms=18)
        retained = store.load_execution_ledger().reservation("reservation-review")
        self.assertEqual((retained.state, retained.host_completed, retained.material_receipt_id), (ExecutionDispatchState.COMPLETE, True, "receipt-review"))

    def test_execution_reservation_checkpoint_and_smaller_retry_converge(self) -> None:
        path = self.root / "console" / "execution-retry-cas.sqlite3"
        store = console.ConsoleStore(path)
        ledger = console.ExecutionDispatchLedger()
        ledger.observe_generation(console.ExecutionConfigGeneration("generation-fast", True, "gpt-5.6", "high", 10, "host:config:fast"))
        ledger.reserve("reservation-retry", "task-retry", "owner-retry", ArtifactIdentity("artifact", "rev-retry", "queue"), observed_at_ms=11)
        ledger.dispatch("reservation-retry", "b" * 64, 900, observed_at_ms=12)
        store.persist_execution_ledger(ledger, now_ms=12)

        ledger.observe_generation(console.ExecutionConfigGeneration("generation-standard", False, "gpt-5.6", "high", 13, "host:config:standard"))
        ledger.checkpoint("reservation-retry", observed_at_ms=14)
        store.persist_execution_ledger(ledger, now_ms=14)
        restarted = store.load_execution_ledger()
        restarted.dispatch("reservation-retry", "c" * 64, 800, observed_at_ms=15)
        restarted.fail_transport(
            "reservation-retry", ExecutionFailureKind.BAD_REQUEST,
            observed_at_ms=16, http_status=400, detail="Bad Request",
        )
        store.persist_execution_ledger(restarted, now_ms=16)
        failed = store.load_execution_ledger().reservation("reservation-retry")
        self.assertEqual((failed.state, failed.failure_kind, failed.retry_count), (ExecutionDispatchState.UNVERIFIED, ExecutionFailureKind.BAD_REQUEST, 0))

        retry_ledger = store.load_execution_ledger()
        retried = retry_ledger.retry_smaller(
            "reservation-retry", ContinuationSnapshot("d" * 64, 800, 600, 17),
            "e" * 64, 550, observed_at_ms=18,
        )
        store.persist_execution_ledger(retry_ledger, now_ms=18)
        store.persist_execution_ledger(retry_ledger, now_ms=18)
        converged = store.load_execution_ledger().reservation("reservation-retry")
        self.assertEqual(
            (converged.state, converged.retry_count, converged.generation_id, converged.requested_service_tier, converged.actual_service_tier),
            (ExecutionDispatchState.ACTIVE, 1, "generation-standard", "default", ""),
        )
        self.assertEqual((retried.requested_fast_mode, retried.service_tier_truth.value), (False, "unverified"))

    def test_execution_generation_legacy_tier_migrates_once_to_boolean_authority(self) -> None:
        path = self.root / "console" / "legacy-execution.sqlite3"
        store = console.ConsoleStore(path)
        payload = {
            "generation_id": "legacy-fast", "service_tier": "priority", "model": "gpt-5.6",
            "effort": "high", "changed_at_ms": 10, "host_receipt_id": "host:config:legacy-fast",
        }
        encoded, digest = store._execution_payload(payload)
        with closing(sqlite3.connect(path)) as connection:
            connection.execute(
                "INSERT INTO execution_config_generations(generation_id,payload_json,payload_digest,changed_at_ms) VALUES(?,?,?,?)",
                ("legacy-fast", encoded, digest, 10),
            )
            connection.commit()
        ledger = store.load_execution_ledger()
        self.assertTrue(ledger.latest_generation.fast_mode)
        self.assertEqual(ledger.latest_generation.requested_service_tier, "fast")
        legacy_generation_digest = ledger.latest_generation.digest
        ledger.reserve(
            "reservation-legacy", "task-legacy", "owner-legacy",
            ArtifactIdentity("artifact", "rev-legacy", "legacy queue"), observed_at_ms=11,
        )
        active = ledger.dispatch("reservation-legacy", "a" * 64, 900, observed_at_ms=12)
        self.assertEqual((active.generation_id, active.requested_service_tier), ("legacy-fast", "fast"))
        store.persist_execution_ledger(ledger, now_ms=13)
        with closing(sqlite3.connect(path)) as connection:
            retained_json, retained_digest = connection.execute(
                "SELECT payload_json,payload_digest FROM execution_config_generations WHERE generation_id='legacy-fast'"
            ).fetchone()
        retained = json.loads(retained_json)
        self.assertEqual(retained["fast_mode"], True)
        self.assertNotIn("service_tier", retained)
        self.assertEqual(store._execution_payload(retained)[1], retained_digest)

        restarted = console.ConsoleStore(path).load_execution_ledger()
        self.assertEqual((len(restarted.generations), restarted.latest_generation.digest), (1, legacy_generation_digest))
        restarted.observe_generation(ExecutionConfigGeneration(
            "generation-standard", False, "gpt-5.6", "high", 20, "host:config:standard",
        ))
        restarted.checkpoint("reservation-legacy", observed_at_ms=21)
        resumed = restarted.dispatch("reservation-legacy", "b" * 64, 800, observed_at_ms=22)
        restarted.fail_transport(
            "reservation-legacy", ExecutionFailureKind.BAD_REQUEST,
            observed_at_ms=23, http_status=400, detail="Bad Request",
        )
        store.persist_execution_ledger(restarted, now_ms=24)
        retry_ledger = console.ConsoleStore(path).load_execution_ledger()
        retried = retry_ledger.retry_smaller(
            "reservation-legacy", ContinuationSnapshot("c" * 64, 800, 600, 25),
            "d" * 64, 550, observed_at_ms=26,
        )
        self.assertEqual((retried.generation_id, retried.requested_service_tier), ("generation-standard", "default"))
        store.persist_execution_ledger(retry_ledger, now_ms=27)
        final = console.ConsoleStore(path).load_execution_ledger()
        self.assertEqual([item.generation_id for item in final.generations], ["legacy-fast", "generation-standard"])

    def test_start_observer_does_not_block_health_on_slow_observation(self) -> None:
        app = console.App(self.codex_home, self.config)
        entered, release = threading.Event(), threading.Event()
        def slow_observation(trigger):
            self.assertEqual(trigger, "startup")
            entered.set()
            release.wait(5)
        with mock.patch.object(app, "observe_once", side_effect=slow_observation) as observe:
            try:
                started = time.monotonic()
                app.start_observer()
                self.assertLess(time.monotonic() - started, 1)
                self.assertTrue(entered.wait(1))
                app.start_observer()
                handler = self._handler("127.0.0.1", "127.0.0.1:4788")
                handler.path = "/healthz"
                handler._json = mock.Mock()
                handler.do_GET()
                self.assertEqual(handler._json.call_args.args[0], console.HTTPStatus.OK)
                self.assertFalse(release.is_set())
                self.assertEqual(observe.call_count, 1)
            finally:
                release.set()
                app.stop_observer()
            self.assertFalse(app._observer_thread.is_alive())

    def test_codex_jsonl_tail_is_bounded_and_missing_usage_stays_unknown(self) -> None:
        session = self.codex_home / "sessions" / "rollout-thread-tail.jsonl"
        session.parent.mkdir(parents=True, exist_ok=True)
        def event(usage):
            return json.dumps({"type": "event_msg", "payload": {
                "type": "token_count", "info": {"total_token_usage": usage},
            }}).encode() + b"\n"
        session.write_bytes(event({"total_tokens": 999}) + b"x" * 2048 + b"\n" + event({"total_tokens": 12}))
        with mock.patch.object(console, "TOKEN_JSONL_TAIL_BYTES", 512), mock.patch.object(console, "TOKEN_JSONL_SCAN_BYTES", 512):
            self.assertEqual(console._codex_jsonl_token_counts(self.codex_home, {"thread-tail"}), {"thread-tail": 12})
            session.write_bytes(event({"total_tokens": 999}) + b"x" * 2048 + b"\n" + event({}))
            self.assertEqual(console._codex_jsonl_token_counts(self.codex_home, {"thread-tail"}), {})
            session.write_bytes(event({"total_tokens": 0}))
            self.assertEqual(console._codex_jsonl_token_counts(self.codex_home, {"thread-tail"}), {"thread-tail": 0})
            session.write_bytes(event({"total_tokens": True}))
            self.assertEqual(console._codex_jsonl_token_counts(self.codex_home, {"thread-tail"}), {})

    def test_codex_usage_host_locator_skips_old_scan_and_repeat_discovery(self) -> None:
        session = self.codex_home / "sessions" / "2026" / "09" / "10" / "rollout-task.jsonl"
        session.parent.mkdir(parents=True)
        session.write_text(json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": 42}}}}) + "\n", encoding="utf-8")
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("ALTER TABLE threads ADD COLUMN rollout_path TEXT")
            connection.execute("UPDATE threads SET rollout_path=? WHERE id='task'", (str(session),))
            connection.commit()
        old = [session.parent / f"older-{i}.jsonl" for i in range(4097)]
        with mock.patch.object(Path, "rglob", return_value=iter([*old, session])) as walk:
            self.assertEqual(console._codex_jsonl_token_counts(self.codex_home, {"task"}), {"task": 42})
            self.assertEqual(console._codex_jsonl_token_counts(self.codex_home, {"task"}), {"task": 42})
            walk.assert_not_called()
        with mock.patch.object(Path, "rglob", side_effect=OSError("discovery unavailable")):
            self.assertEqual(console._codex_jsonl_token_counts(self.codex_home, {"task", "unresolved"}), {"task": 42})
        outside = self.root / "outside-task.jsonl"
        outside.write_bytes(session.read_bytes())
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE threads SET rollout_path=? WHERE id='task'", (str(outside),))
            connection.commit()
        with mock.patch.object(Path, "rglob", return_value=iter([])):
            self.assertEqual(console._codex_jsonl_token_counts(self.codex_home, {"task"}), {})

    def test_codex_jsonl_token_counts_are_high_water_deduped(self) -> None:
        session = self.codex_home / "sessions" / "2026" / "08" / "22" / "rollout-thread-1.jsonl"
        session.parent.mkdir(parents=True)

        def append_event(usage: dict[str, int]) -> None:
            with session.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({
                    "type": "event_msg",
                    "payload": {"type": "token_count", "info": {"total_token_usage": usage}},
                }) + "\n")

        append_event({"input_tokens": 8, "output_tokens": 4})
        store = console.ConsoleStore(self.root / "console" / "console-state.sqlite3")
        overview = {
            "heartbeat_minutes": 30,
            "nodes": [{
                "id": "thread-1", "project_id": "project:alpha", "tokens": 0,
                "status": "active", "updated_at": 2_000_000_000_000,
            }],
            "links": [],
        }
        store.observe_overview(
            overview, now_ms=2_000_000_000_000, trigger="startup", heartbeat_minutes=30,
            codex_home=self.codex_home,
        )
        append_event({"input_tokens": 10, "output_tokens": 8, "total_tokens": 18})
        append_event({"input_tokens": 9, "output_tokens": 6, "total_tokens": 15})
        store.observe_overview(
            overview, now_ms=2_000_000_061_000, trigger="heartbeat", heartbeat_minutes=30,
            codex_home=self.codex_home,
        )
        store.observe_overview(
            overview, now_ms=2_000_000_122_000, trigger="heartbeat", heartbeat_minutes=30,
            codex_home=self.codex_home,
        )

        history = store.token_history(hours=24, before_ms=2_000_000_122_000)
        self.assertEqual(sum(item["delta_tokens"] for item in history), 6)
        self.assertEqual({item["source"] for item in history}, {"codex_jsonl_token_count"})
        connection = sqlite3.connect(self.root / "console" / "console-state.sqlite3")
        try:
            cursor = connection.execute(
                "SELECT cumulative_tokens FROM token_cursors WHERE thread_id='thread-1'"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(cursor[0], 18)

    def test_active_standalone_task_remains_visible_without_ctrl_or_parent(self) -> None:
        now = 2_000_000_000_000
        connection = sqlite3.connect(self.database)
        connection.execute(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("standalone", "🔨DEV - Standalone task", "C:/work/standalone", now // 1000, now, now, now,
             "gpt-5.6-luna", "high", 12, 0, "", "main", "", "", "", 0),
        )
        connection.commit()
        connection.close()

        overview = console.build_overview(self.codex_home, self.config)
        standalone = next(node for node in overview["nodes"] if node["id"] == "standalone")
        self.assertEqual(standalone["role_label"], "TASK")
        self.assertIsNone(standalone["parent_id"])
        self.assertEqual(standalone["controller_ids"], [])
        self.assertEqual(standalone["project_id"], "")
        self.assertFalse(any(project["name"] == "standalone" for project in overview["projects"]))

    def test_usage_history_validates_project_and_ctrl_scopes_without_observing(self) -> None:
        app = console.App(self.codex_home, self.config)
        overview = {
            "nodes": [
                {"id": "ctrl-a", "project_id": "project:a", "role": "ctrl", "virtual": False, "controller_ids": ["ctrl-a"]},
                {"id": "task-a", "project_id": "project:a", "role": "doer", "virtual": False, "controller_ids": ["ctrl-a"]},
                {"id": "ctrl-b", "project_id": "project:b", "role": "ctrl", "virtual": False, "controller_ids": ["ctrl-b"]},
            ],
        }
        history = [{"bucket_ms": 1, "delta_tokens": 7, "source": "host_reported_cumulative_delta"}]
        with mock.patch.object(app, "_host_overview", return_value=overview), \
             mock.patch.object(app.store, "token_history", return_value=history) as token_history, \
             mock.patch.object(app.store, "token_sample_thread_count", return_value=1), \
             mock.patch.object(app, "observe_once", side_effect=AssertionError("usage observation")):
            result = app.usage_history(project_id="ctrl:ctrl-a", hours=24)
            all_projects = app.usage_history(hours=24)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["coverage"], {"observed_threads": 1, "expected_threads": 2})
        self.assertEqual(all_projects["status"], "partial")
        self.assertEqual(all_projects["coverage"], {"observed_threads": 1, "expected_threads": 3})
        self.assertEqual(result["total_tokens"], 7)
        self.assertEqual(set(result["status_claim"]), {"no_data", "partial", "ok"})
        token_history.assert_has_calls([
            mock.call(project_id=None, thread_ids={"ctrl-a", "task-a"}, hours=24, after_ms=mock.ANY, before_ms=mock.ANY),
            mock.call(project_id=None, thread_ids=None, hours=24, after_ms=mock.ANY, before_ms=mock.ANY),
        ])
        self.assertEqual(token_history.call_count, 2)
        with mock.patch.object(app, "_host_overview", return_value=overview):
            with self.assertRaises(console.ConsoleError):
                app.usage_history(project_id="missing", hours=24)
            with self.assertRaises(console.ConsoleError):
                app.usage_history(project_id="project:a", ctrl_id="ctrl-b", hours=24)
            with self.assertRaises(console.ConsoleError):
                app.usage_history(hours=2)

    def test_task_usage_ranks_persisted_window_deltas_and_preserves_scope(self) -> None:
        app = console.App(self.codex_home, self.config)
        now = 2_000_000_000_000
        hour = 3_600_000
        nodes = [
            {"id": "a", "title": "Alpha", "project_id": "project:a", "controller_ids": ["ctrl-a"]},
            {"id": "b", "title": "Beta", "project_id": "project:a", "controller_ids": ["ctrl-b"]},
            {"id": "zero", "title": "Zero", "project_id": "project:a", "controller_ids": ["ctrl-a"]},
            {"id": "missing", "title": "Missing", "project_id": "project:a", "controller_ids": ["ctrl-a"]},
            {"id": "foreign", "title": "Foreign", "project_id": "project:b", "controller_ids": ["ctrl-c"]},
        ]
        records = [
            (now-hour, "a", "project:a", 3),
            (now-1, "a", "project:a", 2),
            (now-hour-1, "b", "project:a", 20),
            (now-1, "b", "project:a", 8),
            (now-1, "zero", "project:a", 0),
            (now-168*hour, "a", "project:a", 100),
            (now-168*hour-1, "a", "project:a", 1000),
            (now+1, "a", "project:a", 2000),
            (now-1, "foreign", "project:b", 9000),
            (now-2, "a", "project:b", 8000),
            (now-1, "not-host-bound", "project:a", 7000),
        ]
        with closing(app.store._connect()) as db:
            db.executemany(
                "INSERT INTO token_samples VALUES (?,?,?,?,?,?,?)",
                [(stamp, stamp, project, task, 999999, delta, "sqlite")
                 for stamp, task, project, delta in records],
            )
            db.commit()
        scope = {"type": "project", "project_id": "project:a"}
        with mock.patch.object(console.time, "time", return_value=now/1000), \
             mock.patch.object(app, "_observed_scope", return_value=({}, nodes[:4], {"a", "b", "zero", "missing"}, scope)), \
             mock.patch.object(app, "_verified_yield", return_value={}), \
             mock.patch.object(app, "observe_once", side_effect=AssertionError("read mutated observer")):
            one = app.usage_history(project_id="project:a", hours=1)
            day = app.usage_history(project_id="project:a", hours=24)
            week = app.usage_history(project_id="project:a", hours=168)
            self.assertEqual(app.usage_history(hours=12)["task_usage"], day["task_usage"])
            self.assertEqual([(r["thread_id"], r["tokens"]) for r in one["task_usage"]],
                             [("b", 8), ("a", 5), ("zero", 0)])
            self.assertEqual([(r["thread_id"], r["tokens"]) for r in week["task_usage"]],
                             [("a", 105), ("b", 28), ("zero", 0)])
            self.assertEqual(one["task_usage_status"], "partial")
            self.assertEqual(one["task_usage_coverage"], {"observed_threads": 3, "expected_threads": 4})
            self.assertEqual(one["task_usage"][0]["title"], "Beta")
            for invalid in (True, 1.0, 2, 169):
                with self.assertRaises(console.ConsoleError):
                    app.usage_history(hours=invalid)
        with mock.patch.object(console.time, "time", return_value=now/1000):
            restarted = console.ConsoleStore(app.store.path)
            self.assertEqual(restarted.token_sample_series(
                project_id="project:a", thread_ids={"zero"}, hours=1, by_task=True,
            )[0]["tokens"], 0)
            self.assertEqual(restarted.token_sample_series(
                project_id="project:a", thread_ids=set(), hours=168, by_task=True), [])
            self.assertEqual([(r["task_id"], r["tokens"]) for r in restarted.token_sample_series(
                project_id="project:a", thread_ids={"a"}, hours=1, by_task=True)], [("a", 5)])
        with mock.patch.object(app, "_observed_scope", return_value=({}, [], set(), scope)), \
             mock.patch.object(app, "_verified_yield", return_value={}):
            empty = app.usage_history(hours=168)
            self.assertEqual(empty["task_usage"], [])
            self.assertEqual(empty["task_usage_status"], "no_data")

    def test_usage_history_explicit_range_month_and_task_rate_provenance(self) -> None:
        app = console.App(self.codex_home, self.config)
        now, minute = 2_000_000_000_000, 60_000
        start = now - 10 * minute
        nodes = [{"id": "a", "title": "Alpha", "project_id": "project:a", "model": "current-not-history"},
                 {"id": "b", "title": "Beta", "project_id": "project:a"},
                 {"id": "missing", "title": "Missing", "project_id": "project:a"}]
        samples = [(start - 1, "a", "project:a", 999),
                   (start, "a", "project:a", 10), (start + minute, "a", "project:a", 20),
                   (start + 3 * minute, "a", "project:a", 60),
                   (start + 6 * minute, "a", "project:a", 30),
                   (start + 7 * minute, "a", "project:a", 20),
                   (start + minute, "b", "project:a", 0),
                   (start + 2 * minute, "b", "project:a", 0),
                   (start + minute, "foreign", "project:b", 9999),
                   (start + 2 * minute, "a", "project:b", 8888),
                   (now - 30 * 86_400_000, "a", "project:a", 7),
                   (now - 30 * 86_400_000 - 1, "a", "project:a", 7777),
                   (now + 1, "a", "project:a", 9999)]
        with closing(app.store._connect()) as db:
            db.executemany("INSERT INTO token_samples VALUES (?,?,?,?,?,?,?)",
                           [(stamp, stamp, project, task, 99999999, tokens, "sqlite")
                            for stamp, task, project, tokens in samples])
            db.commit()
        scope = {"type": "project", "project_id": "project:a"}
        with mock.patch.object(console.time, "time", return_value=now/1000), \
             mock.patch.object(app, "_observed_scope", return_value=({}, nodes, {"a", "b", "missing"}, scope)), \
             mock.patch.object(app, "_verified_yield", return_value={}), \
             mock.patch.object(app, "observe_once", side_effect=AssertionError("read-only")):
            result = app.usage_history(project_id="project:a", after_ms=start, before_ms=now)
            self.assertEqual(result["window"], {"after_ms": start, "before_ms": now, "explicit": True, "retention_days": 30})
            exact_end = app.usage_history(after_ms=start, before_ms=start + 5 * minute)
            self.assertTrue(all(row["bucket_start_ms"] < row["bucket_end_ms"] for row in exact_end["task_history"]["items"]))
            self.assertEqual(result["task_history"]["total_tokens"], 140)
            self.assertEqual(sum(row["tokens"] for row in result["task_usage"]), 140)
            rows = result["task_history"]["items"]
            a = [row for row in rows if row["thread_id"] == "a"]
            self.assertEqual([row["tokens_per_minute"] for row in a], [26.67, 20.0])
            self.assertEqual([row["observed_interval_ms"] for row in a], [3 * minute, minute])
            self.assertEqual([row["rate_tokens"] for row in a], [80, 20])
            self.assertEqual([row["rate_sample_count"] for row in a], [2, 1])
            # First interval crosses the selected start; the 3->6 interval crosses bins.
            # Neither contributes tokens or elapsed time to the reported bin rate.
            self.assertTrue(all(row["model"] is None and row["model_status"] == "UNKNOWN" for row in rows))
            self.assertEqual(len(rows), 3)  # Missing buckets/threads never become zero points.
            self.assertEqual(rows[-1]["bucket_start_ms"], start + 5 * minute)
            self.assertEqual(result["task_history"]["coverage"], {"observed_threads": 2, "expected_threads": 3})
            self.assertIsNone(result["usage_now"]["rate_tokens_per_minute"])
            self.assertIsNone(result["usage_now"]["rate_sampled_at_ms"])
            self.assertTrue(all(row["tokens_per_minute"] is None for row in result["rate_history"]))
            self.assertEqual(result["account_history"]["status"], "no_data")
            month = app.usage_history(hours=720)
            self.assertEqual(month["task_history"]["total_tokens"], 1146)  # exact 30-day edge included
            self.assertEqual(month["window"]["after_ms"], now - 30 * 86_400_000)
            historical = app.usage_history(after_ms=start, before_ms=start + minute)
            self.assertEqual(historical["task_history"]["total_tokens"], 30)
            self.assertTrue(all(row["bucket_end_ms"] <= start + minute for row in historical["task_history"]["items"]))
            for bounds in ({"after_ms": start}, {"before_ms": now},
                           {"after_ms": True, "before_ms": now}, {"after_ms": start, "before_ms": now + 1},
                           {"after_ms": now, "before_ms": start},
                           {"after_ms": now - 31 * 86_400_000, "before_ms": now}):
                with self.assertRaises(console.ConsoleError):
                    app.usage_history(**bounds)
            app.store = console.ConsoleStore(app.store.path)
            self.assertEqual(app.usage_history(after_ms=start, before_ms=now)["task_history"], result["task_history"])
        with mock.patch.object(console.time, "time", return_value=now/1000), \
             mock.patch.object(app, "_observed_scope", return_value=({}, [nodes[1]], {"b"}, {"type": "ctrl", "ctrl_id": "ctrl-b"})), \
             mock.patch.object(app, "_verified_yield", return_value={}):
            scoped = app.usage_history(after_ms=start, before_ms=now)
            self.assertTrue(all(row["thread_id"] == "b" for row in scoped["task_history"]["items"]))
            self.assertEqual(scoped["task_history"]["total_tokens"], 0)  # observed zero, not absence
            self.assertEqual(scoped["task_history"]["items"][-1]["tokens_per_minute"], 0)
            self.assertEqual(scoped["usage_now"]["rate_tokens_per_minute"], 0)
        with mock.patch.object(console.time, "time", return_value=now/1000), \
             mock.patch.object(app, "_observed_scope", return_value=({}, [nodes[0]], {"a"}, scope)), \
             mock.patch.object(app, "_verified_yield", return_value={}):
            single = app.usage_history(after_ms=start, before_ms=now)
            self.assertEqual(single["usage_now"]["rate_tokens_per_minute"], 25.0)  # qualified100 /4min, not140/7min
            self.assertEqual([row["tokens_per_minute"] for row in single["rate_history"]], [26.67, 20.0])
        with closing(app.store._connect()) as db:
            db.executemany("INSERT INTO token_samples VALUES (?,?,?,?,?,?,?)",
                           [(stamp, stamp, "project:a", "late", 999, tokens, "sqlite")
                            for stamp, tokens in ((start, 10), (start + minute, 20), (now - 1, 30))])
            db.commit()
        with mock.patch.object(console.time, "time", return_value=now/1000), \
             mock.patch.object(app, "_observed_scope", return_value=({}, [{"id": "late", "project_id": "project:a"}], {"late"}, scope)), \
             mock.patch.object(app, "_verified_yield", return_value={}):
            late = app.usage_history(after_ms=start, before_ms=now)["usage_now"]
            self.assertEqual(late["sampled_at_ms"], now - 1)
            self.assertEqual(late["rate_sampled_at_ms"], start + minute)
            self.assertEqual(late["rate_tokens_per_minute"], 20.0)

    def test_task_rate_history_exact_project_filter_precedes_cap(self) -> None:
        app = console.App(self.codex_home, self.config)
        with closing(app.store._connect()) as db:
            db.executemany("INSERT INTO token_samples VALUES (?,?,?,?,?,?,?)",
                           [(index * 60_000, index * 60_000, "stale-project", "a", index, 1, "sqlite")
                            for index in range(10002)])
            db.execute("INSERT INTO token_samples VALUES (?,?,?,?,?,?,?)",
                       (10003 * 60_000, 10003 * 60_000, "project:a", "a", 999999, 5, "sqlite"))
            db.commit()
        rows = app.store.token_sample_series(
            project_id=None, thread_ids={"a"}, after_ms=0, before_ms=10004 * 60_000,
            bucket_width_ms=60_000, task_projects={"a": "project:a"},
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["project_id"], rows[0]["tokens"], rows[0]["tokens_per_minute"]),
                         ("project:a", 5, None))

    def test_usage_forecast_requires_explicit_inputs_and_observed_rate(self) -> None:
        app = console.App(self.codex_home, self.config)
        overview = {
            "nodes": [
                {"id": "ctrl-a", "project_id": "project:a", "role": "ctrl", "virtual": False, "controller_ids": ["ctrl-a"]},
            ],
        }
        one_hour_history = [
            {"bucket_ms": 1_000_000, "delta_tokens": 200, "source": "codex_jsonl_token_count"},
            {"bucket_ms": 1_060_000, "delta_tokens": 100, "source": "codex_jsonl_token_count"},
        ]
        twelve_hour_history = [
            {"bucket_ms": 800_000, "delta_tokens": 100, "source": "codex_jsonl_token_count"},
            {"bucket_ms": 1_100_000, "delta_tokens": 100, "source": "codex_jsonl_token_count"},
        ]
        def samples(**kw):
            if not kw.get("bucket_width_ms"):
                return []
            start, end = ((1_000_000, 1_060_000) if kw["hours"] == 1 else (800_000, 1_100_000))
            return [{"thread_id": "ctrl-a", "project_id": "project:a", "bucket_start_ms": start,
                     "bucket_end_ms": end, "rate_start_ms": start, "rate_end_ms": end,
                     "observed_interval_ms": end - start, "rate_tokens": 100}]
        with mock.patch.object(app, "_host_overview", return_value=overview), \
             mock.patch.object(
                 app.store,
                 "token_history",
                 side_effect=[one_hour_history, one_hour_history, twelve_hour_history],
             ), \
             mock.patch.object(app.store, "token_sample_thread_count", return_value=1), \
             mock.patch.object(app.store, "token_sample_series", side_effect=samples), \
             mock.patch.object(console.time, "time", return_value=1_100):
            missing = app.usage_history(hours=1)
            one_hour = app.usage_history(
                hours=1,
                target_reset_at_ms=2_000_000,
                remaining_token_budget=600,
            )
            twelve_hours = app.usage_history(
                hours=12,
                target_reset_at_ms=2_000_000,
                remaining_token_budget=600,
            )
        self.assertEqual(missing["forecast"]["status"], "no_data")
        self.assertEqual(missing["forecast"]["exhaustion_at_ms"], None)
        self.assertEqual(
            missing["forecast"]["missing_inputs"],
            ["remaining_token_budget", "target_reset_at_ms"],
        )
        self.assertEqual(one_hour["usage_now"]["tokens"], 300)
        self.assertEqual(one_hour["usage_now"]["sampled_at_ms"], 1_060_000)
        self.assertEqual(one_hour["forecast"]["status"], "estimated")
        self.assertEqual(one_hour["forecast"]["remaining_token_budget"], 600)
        self.assertEqual(one_hour["forecast"]["remaining_tokens"], 600)
        self.assertEqual(one_hour["usage_now"]["rate_tokens_per_minute"], 100.0)
        self.assertEqual(one_hour["forecast"]["exhaustion_at_ms"], 1_460_000)
        self.assertTrue(one_hour["forecast"]["exhausts_before_reset"])
        self.assertEqual(twelve_hours["forecast"]["remaining_token_budget"], 600)
        self.assertEqual(twelve_hours["forecast"]["remaining_tokens"], 600)
        self.assertNotEqual(one_hour["tokens_per_minute"], twelve_hours["tokens_per_minute"])
        self.assertNotEqual(
            one_hour["forecast"]["exhaustion_at_ms"],
            twelve_hours["forecast"]["exhaustion_at_ms"],
        )
        self.assertIn("not provider billing", one_hour["forecast"]["claim_limit"])

    def test_usage_forecast_stays_no_data_without_history_or_positive_rate(self) -> None:
        app = console.App(self.codex_home, self.config)
        overview = {"nodes": []}
        with mock.patch.object(app, "_host_overview", return_value=overview), \
             mock.patch.object(app.store, "token_history", return_value=[]), \
             mock.patch.object(app.store, "token_sample_thread_count", return_value=0), \
             mock.patch.object(console.time, "time", return_value=1_000):
            result = app.usage_history(
                hours=24,
                target_reset_at_ms=2_000_000,
                remaining_token_budget=600,
            )
        self.assertEqual(result["usage_now"]["status"], "no_data")
        self.assertIsNone(result["usage_now"]["tokens"])
        self.assertEqual(result["forecast"]["status"], "no_data")
        self.assertIn("usage_history", result["forecast"]["missing_inputs"])
        self.assertIn("positive_observed_rate", result["forecast"]["missing_inputs"])
        with self.assertRaises(console.ConsoleError):
            app.usage_history(hours=24, remaining_token_budget=-1)

    def test_usage_history_projects_verified_yield_without_changing_completion(self) -> None:
        app = console.App(self.codex_home, self.config)
        app.progress_ledger.append({
            "schema_version": 1,
            "event_id": "yield-proof",
            "dedupe_key": "yield-proof-dedupe",
            "portfolio_id": "portfolio-main",
            "project_id": "project:alpha",
            "ctrl_id": "root",
            "milestone_id": "milestone-one",
            "block_id": "block-one",
            "task_id": "root",
            "owner_id": "owner-root",
            "scope_version": 1,
            "parent_block_id": None,
            "dependency_ids": [],
            "lineage": {"predecessor_block_ids": [], "split_from": None, "merged_from": []},
            "event_kind": "BLOCK_CREATED",
            "lifecycle_state": "VERIFIED",
            "measurement": {
                "state": "MEASURED", "committed_weight": 10,
                "admitted_proof_weight": 5, "basis_receipt_ids": ["scope-weight"],
            },
            "proof": {
                "required_classes": ["SOURCE"], "receipt_ids": ["accepted-proof"],
                "claim_limit": "Source proof only.",
            },
            "eta": {"start_ms": None, "end_ms": None, "confidence": None, "basis_receipt_ids": []},
            "rework": {"attempt": 1, "count": 0, "invalidated_receipt_ids": []},
            "custody": {"surface": "surface:block-one", "receipt_id": "custody-one"},
            "steering_receipt_ids": [],
            "material_update_sentence": "The accepted proof is admitted.",
            "flags": ["proof"],
            "provenance": "typed owner material boundary",
            "source": "swarm_runtime",
            "observed_at_ms": 1_050_000,
            "causation_id": None,
            "parent_event_id": None,
        })
        overview = {
            "nodes": [
                {"id": "root", "project_id": "project:alpha", "role": "ctrl", "virtual": False, "controller_ids": ["root"]},
            ],
        }
        history = [{"bucket_ms": 1_060_000, "delta_tokens": 1_000, "source": "codex_jsonl_token_count"}]
        samples = [{"task_id": "root", "observed_at_ms": 1_060_000, "tokens": 1_000}]
        with mock.patch.object(app, "_host_overview", return_value=overview), \
             mock.patch.object(app.store, "token_history", return_value=history), \
             mock.patch.object(app.store, "token_sample_thread_count", return_value=1), \
             mock.patch.object(app.store, "token_sample_series", side_effect=lambda **kw: [] if kw.get("by_task") or kw.get("bucket_width_ms") else samples), \
             mock.patch.object(console.time, "time", return_value=1_100):
            result = app.usage_history(project_id="project:alpha", hours=1)

        verified = result["verified_yield"]
        self.assertEqual(verified["projects"][0]["net_scope_points"], 50.0)
        self.assertEqual(verified["projects"][0]["yield_per_100k"], 5_000.0)
        self.assertEqual(verified["portfolio"]["yield_per_100k"], 5_000.0)
        self.assertEqual(verified["tasks"][0]["scope"]["id"], "root")
        self.assertNotIn("percent", verified["projects"][0])
        self.assertFalse(result["usage_consumed"])

    def test_progress_summary_aggregates_only_compatible_receipt_backed_units(self) -> None:
        def measured(
            task_id: str,
            completed: int,
            basis: str = "accepted milestones",
            *,
            plan_id: str = "plan-alpha",
            unit_kind: str = "milestone",
            include_identity: bool = True,
        ) -> dict[str, object]:
            plan_units: dict[str, object] = {
                "total_units": 4,
                "completed_units": completed,
                "basis": basis,
                "observed_at_ms": 1_000 + completed,
            }
            if include_identity:
                plan_units.update({
                    "plan_id": plan_id,
                    "unit_id": f"unit-{task_id}",
                    "unit_kind": unit_kind,
                })
            return {
                "id": task_id,
                "project_id": "project:a",
                "role": "doer",
                "status": "active",
                "virtual": False,
                "is_subagent": False,
                "controller_ids": ["ctrl-a"],
                "eta": {
                    "trigger": "task_owner_report",
                    "receipt_source": f"owner:{task_id}:receipt-{task_id}",
                    "progress_basis": {
                        "receipts": [f"receipt-{task_id}"],
                        "plan_units": plan_units,
                    },
                },
                "proof_snapshot": {"media": []},
            }

        summary = console.App._progress_for_nodes(
            [measured("one", 1), measured("two", 3, basis="reviewed checkpoints")],
            {"type": "ctrl", "ctrl_id": "ctrl-a", "project_id": "project:a"},
        )
        self.assertEqual(summary["progress"]["percent"], 50.0)
        self.assertEqual(summary["progress"]["completed_units"], 4)
        self.assertEqual(summary["progress"]["total_units"], 8)
        self.assertEqual(summary["measurement_status"], "measured")
        self.assertEqual(summary["progress"]["plan_id"], "plan-alpha")
        self.assertEqual(summary["progress"]["unit_kind"], "milestone")
        self.assertEqual(summary["progress"]["unit_ids"], ["unit-one", "unit-two"])
        self.assertEqual(summary["progress"]["basis"], "Receipt-backed plan units")
        self.assertEqual(summary["tasks"][0]["progress"]["source"], "task_owner_report")
        self.assertIn("does not prove", summary["tasks"][0]["progress"]["claim_limit"])
        self.assertEqual(summary["freshness"]["state"], "fresh")
        # Aggregate freshness is coverage-aware: the oldest included unit is authoritative.
        self.assertEqual(summary["freshness"]["observed_at_ms"], 1_001)
        stale = console.App._progress_for_nodes(
            [measured("one", 1), measured("two", 3, basis="reviewed checkpoints")],
            {"type": "ctrl", "ctrl_id": "ctrl-a", "project_id": "project:a"},
            now_ms=10_000,
            stale_after_ms=1_000,
        )
        self.assertEqual(stale["freshness"]["state"], "stale")
        self.assertEqual(stale["freshness"]["age_ms"], 8_999)
        payload = console.App._progress_payload({
            "nodes": [measured("one", 1), measured("two", 3, basis="reviewed checkpoints")],
            "projects": [{"id": "project:a"}],
            "controllers": [{"id": "ctrl-a", "project_id": "project:a"}],
        })
        self.assertIsNone(payload["projects"]["project:a"]["progress"])
        self.assertIsNone(payload["controllers"]["ctrl-a"]["progress"])
        self.assertEqual(payload["controllers"]["ctrl-a"]["measurement_authority"], "direct_ctrl_receipt")

        missing = console.App._progress_for_nodes(
            [measured("one", 1), {**measured("two", 3), "eta": {}}],
            {"type": "project", "project_id": "project:a"},
        )
        self.assertIsNone(missing["progress"])
        self.assertEqual(missing["progress_display"], "Unmeasured")
        self.assertEqual(missing["unmeasured_reason"], "missing_receipt_backed_units")
        self.assertEqual(missing["freshness"]["state"], "unavailable")

        heterogeneous = console.App._progress_for_nodes(
            [measured("one", 1), measured("two", 3, plan_id="plan-beta")],
            {"type": "project", "project_id": "project:a"},
        )
        self.assertIsNone(heterogeneous["progress"])
        self.assertEqual(heterogeneous["unmeasured_reason"], "heterogeneous_plan_units")

        missing_identity = console.App._progress_for_nodes(
            [measured("one", 1), measured("two", 3, include_identity=False)],
            {"type": "project", "project_id": "project:a"},
        )
        self.assertIsNone(missing_identity["progress"])
        self.assertEqual(missing_identity["unmeasured_reason"], "missing_receipt_backed_units")

    def test_progress_payload_isolates_direct_ctrl_measures_without_subordinate_double_count(self) -> None:
        def ctrl_node(ctrl_id: str, completed: int | None, unit_id: str) -> dict[str, object]:
            eta = None if completed is None else {
                "trigger": "task_owner_report",
                "receipt_source": f"instruction_only_local_sidecar:{ctrl_id}",
                "progress_source": "instruction_only_local_sidecar",
                "progress_basis": {
                    "receipts": [f"receipt-{ctrl_id}"],
                    "plan_units": {
                        "plan_id": "shared-project-plan",
                        "unit_id": unit_id,
                        "unit_kind": "ctrl_scope",
                        "total_units": 4,
                        "completed_units": completed,
                        "basis": "CTRL accepted milestones",
                        "observed_at_ms": 1_000 + int(completed or 0),
                    },
                },
            }
            return {
                "id": ctrl_id, "project_id": "project:a", "role": "ctrl", "status": "active",
                "virtual": False, "is_subagent": False, "controller_ids": [ctrl_id],
                "eta": eta, "proof_snapshot": {"media": []},
            }

        subordinate = {
            "id": "task-a", "project_id": "project:a", "role": "doer", "status": "active",
            "virtual": False, "is_subagent": False, "controller_ids": ["ctrl-a", "ctrl-b"],
            "eta": {
                "trigger": "task_owner_report", "receipt_source": "task:receipt",
                "progress_basis": {
                    "receipts": ["task-receipt"],
                    "plan_units": {
                        "plan_id": "shared-project-plan", "unit_id": "subordinate-overlap",
                        "unit_kind": "ctrl_scope", "total_units": 100, "completed_units": 100,
                        "basis": "Subordinate status", "observed_at_ms": 2_000,
                    },
                },
            },
            "proof_snapshot": {"media": []},
        }
        controllers = [
            {"id": ctrl_id, "project_id": "project:a", "archived": False,
             "controller_classification": "swarm_ctrl", "controller_classification_source": "host_threads.agent_role"}
            for ctrl_id in ("ctrl-a", "ctrl-b")
        ]
        view = {
            "nodes": [ctrl_node("ctrl-a", 1, "ctrl-unit-a"), ctrl_node("ctrl-b", 3, "ctrl-unit-b"), subordinate],
            "projects": [{"id": "project:a"}], "controllers": controllers, "heartbeat_minutes": 30,
        }
        with mock.patch.object(console.time, "time", return_value=2):
            payload = console.App._progress_payload(view)
        self.assertEqual(payload["controllers"]["ctrl-a"]["progress"]["percent"], 25.0)
        self.assertEqual(payload["controllers"]["ctrl-b"]["progress"]["percent"], 75.0)
        self.assertEqual(payload["projects"]["project:a"]["progress"]["percent"], 50.0)
        self.assertEqual(payload["projects"]["project:a"]["progress"]["total_units"], 8)
        self.assertEqual(payload["all_projects"]["progress"]["total_units"], 8)
        self.assertEqual(payload["projects"]["project:a"]["progress"]["authority"], "direct_ctrl_receipt")

        view["nodes"][1]["eta"] = None
        with mock.patch.object(console.time, "time", return_value=2):
            missing = console.App._progress_payload(view)
        self.assertEqual(missing["controllers"]["ctrl-a"]["progress"]["percent"], 25.0)
        self.assertIsNone(missing["controllers"]["ctrl-b"]["progress"])
        self.assertIsNone(missing["projects"]["project:a"]["progress"])
        self.assertIsNone(missing["all_projects"]["progress"])

        app = console.App(self.codex_home, self.config)
        ctrl_scope = {"type": "ctrl", "ctrl_id": "ctrl-a", "project_id": "project:a"}
        with mock.patch.object(app, "_observed_scope", return_value=(view, view["nodes"], None, ctrl_scope)), \
             mock.patch.object(app, "overview", return_value={"progress": missing}):
            endpoint = app.progress_summary(ctrl_id="ctrl-a")
        self.assertEqual(endpoint["progress"]["percent"], 25.0)
        self.assertEqual(endpoint["measurement_authority"], "direct_ctrl_receipt")

        view["nodes"][0]["eta"] = None
        with mock.patch.object(console.time, "time", return_value=2):
            no_direct = console.App._progress_payload(view)
        with mock.patch.object(app, "_observed_scope", return_value=(view, view["nodes"], None, ctrl_scope)), \
             mock.patch.object(app, "overview", return_value={"progress": no_direct}):
            endpoint = app.progress_summary(ctrl_id="ctrl-a")
        self.assertIsNone(endpoint["progress"])
        self.assertEqual(endpoint["measurement_authority"], "direct_ctrl_receipt")

    @staticmethod
    def _ctrl_progress_pulse(
        task_id: str,
        project_id: str,
        *,
        observed_at_ms: int,
        pulse_receipt: str,
        completed_units: int | None,
    ) -> dict[str, object]:
        progress = None if completed_units is None else {
            "receipt_id": "material-4-of-5",
            "plan_id": "plan-five-steps",
            "previous_plan_id": None,
            "unit_id": "ctrl-project-plan",
            "unit_kind": "accepted_step",
            "total_units": 5,
            "completed_units": completed_units,
            "basis": "Accepted and frozen plan steps",
            "observed_at_ms": observed_at_ms,
            "source": "task_owner:local",
        }
        return {
            "schema_version": 1,
            "source": "swarm_local_progress_sidecar",
            "receipt_type": "swarm_ctrl_project_pulse",
            "task_id": task_id,
            "project_id": project_id,
            "pulse_receipt": pulse_receipt,
            "observed_at_ms": observed_at_ms,
            "state": "in_progress",
            "progress": progress,
            "eta_report": None,
        }

    def test_progress_read_ingests_new_ctrl_pulse_once_and_preserves_liveness_only_update(self) -> None:
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE threads SET agent_role='ctrl' WHERE id='root'")
            connection.commit()
        app = console.App(self.codex_home, self.config, state_path=self.root / "console-state.sqlite3")
        initial = app.overview()
        ctrl_node = next(node for node in initial["nodes"] if node["id"] == "root")
        project_id = ctrl_node["project_id"]
        observed_at_ms = 1_000_000
        write_progress_pulse(
            self.codex_home,
            self._ctrl_progress_pulse(
                "root", project_id,
                observed_at_ms=observed_at_ms,
                pulse_receipt="pulse-material",
                completed_units=4,
            ),
        )

        progress_endpoint = app.progress_summary(ctrl_id="root")
        self.assertEqual(progress_endpoint["progress"]["percent"], 80.0)
        material = app.overview()
        ctrl_summary = material["progress"]["controllers"]["root"]
        project_summary = material["progress"]["projects"][project_id]
        self.assertEqual(ctrl_summary["progress"]["percent"], 80.0)
        self.assertEqual(project_summary["progress"]["percent"], 80.0)
        with closing(sqlite3.connect(app.store.path)) as connection:
            receipt_count = connection.execute("SELECT COUNT(*) FROM task_progress_receipts").fetchone()[0]
            pulse_row = connection.execute(
                "SELECT payload_digest, updated_at_ms FROM task_progress_pulse_files"
            ).fetchone()
        app.overview()
        with closing(sqlite3.connect(app.store.path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM task_progress_receipts").fetchone()[0], receipt_count)
            self.assertEqual(
                connection.execute("SELECT payload_digest, updated_at_ms FROM task_progress_pulse_files").fetchone(),
                pulse_row,
            )

        heartbeat_at_ms = observed_at_ms + 100
        write_progress_pulse(
            self.codex_home,
            self._ctrl_progress_pulse(
                "root", project_id,
                observed_at_ms=heartbeat_at_ms,
                pulse_receipt="pulse-heartbeat",
                completed_units=None,
            ),
        )
        heartbeat = app.overview()
        heartbeat_ctrl = heartbeat["progress"]["controllers"]["root"]
        heartbeat_node = next(node for node in heartbeat["nodes"] if node["id"] == "root")
        self.assertEqual(heartbeat_ctrl["progress"]["percent"], 80.0)
        self.assertEqual(heartbeat_ctrl["progress"]["observed_at_ms"], observed_at_ms)
        self.assertEqual(heartbeat_node["eta"]["pulse_observed_at_ms"], heartbeat_at_ms)
        with closing(sqlite3.connect(app.store.path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM task_progress_receipts").fetchone()[0], receipt_count)

    def test_progress_read_retries_unchanged_pulse_after_late_host_observation(self) -> None:
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE threads SET agent_role='ctrl' WHERE id='root'")
            connection.commit()
        observed = console.build_overview(self.codex_home, self.config)
        ctrl_node = next(node for node in observed["nodes"] if node["id"] == "root")
        project_id = ctrl_node["project_id"]
        missing_task = copy.deepcopy(observed)
        missing_task["nodes"] = [node for node in missing_task["nodes"] if node["id"] != "root"]
        missing_task["controllers"] = [controller for controller in missing_task["controllers"] if controller["id"] != "root"]
        missing_task["roots"] = [node_id for node_id in missing_task["roots"] if node_id != "root"]
        app = console.App(self.codex_home, self.config, state_path=self.root / "console-late-host.sqlite3")
        with app.overview_lock:
            app._overview = missing_task
            app._overview_revision = 1
        write_progress_pulse(
            self.codex_home,
            self._ctrl_progress_pulse(
                "root", project_id,
                observed_at_ms=1_000_000,
                pulse_receipt="pulse-before-host",
                completed_units=4,
            ),
        )

        first = app.overview()
        self.assertNotIn("root", first["progress"]["controllers"])
        self.assertEqual(app.store.latest_progress(), {})
        self.assertNotEqual(app._progress_pulse_fingerprint, console.progress_pulse_fingerprint(self.codex_home))
        with app.overview_lock:
            app._overview = observed
            app._overview_revision += 1
        retried = app.overview()
        self.assertEqual(retried["progress"]["controllers"]["root"]["progress"]["percent"], 80.0)

    def test_progress_read_retries_unchanged_pulse_after_transient_import_failure(self) -> None:
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE threads SET agent_role='ctrl' WHERE id='root'")
            connection.commit()
        app = console.App(self.codex_home, self.config, state_path=self.root / "console-transient.sqlite3")
        initial = app.overview()
        ctrl_node = next(node for node in initial["nodes"] if node["id"] == "root")
        project_id = ctrl_node["project_id"]
        write_progress_pulse(
            self.codex_home,
            self._ctrl_progress_pulse(
                "root", project_id,
                observed_at_ms=1_000_000,
                pulse_receipt="pulse-transient",
                completed_units=4,
            ),
        )

        with mock.patch.object(app.store, "ingest_progress_pulses", side_effect=sqlite3.OperationalError("busy")):
            failed = app.overview()
        self.assertIsNone(failed["progress"]["controllers"]["root"]["progress"])
        self.assertNotEqual(app._progress_pulse_fingerprint, console.progress_pulse_fingerprint(self.codex_home))
        retried = app.overview()
        self.assertEqual(retried["progress"]["controllers"]["root"]["progress"]["percent"], 80.0)

    def test_valid_ctrl_pulse_without_host_role_is_explicitly_unclassified(self) -> None:
        app = console.App(self.codex_home, self.config, state_path=self.root / "console-unclassified.sqlite3")
        initial = app.overview()
        ctrl_node = next(node for node in initial["nodes"] if node["id"] == "root")
        project_id = ctrl_node["project_id"]
        write_progress_pulse(
            self.codex_home,
            self._ctrl_progress_pulse(
                "root", project_id,
                observed_at_ms=1_000_000,
                pulse_receipt="pulse-unclassified",
                completed_units=4,
            ),
        )
        result = app.overview()["progress"]["controllers"]["root"]
        self.assertIsNone(result["progress"])
        self.assertEqual(result["progress_display"], "Unmeasured")
        self.assertEqual(result["unmeasured_reason"], "unclassified_ctrl")
        self.assertEqual(result["measurement_authority"], "direct_ctrl_receipt")
        endpoint = app.progress_summary(ctrl_id="root")
        self.assertIsNone(endpoint["progress"])
        self.assertEqual(endpoint["unmeasured_reason"], "unclassified_ctrl")

    def test_progress_summary_never_uses_unbound_measurement_or_task_status_as_percentage(self) -> None:
        nodes = [
            {"id": "done", "project_id": "project:a", "role": "doer", "status": "done", "virtual": False, "is_subagent": False, "controller_ids": ["ctrl-a"], "proof_snapshot": {"media": [{"evidence_id": "proof-1"}]}},
            {"id": "blocked", "project_id": "project:a", "role": "doer", "status": "quiet", "virtual": False, "is_subagent": False, "controller_ids": ["ctrl-a"], "eta": {"status": "blocked", "reason": "Dependency is not complete."}, "proof_snapshot": {"media": []}},
            {"id": "forged", "project_id": "project:a", "role": "doer", "status": "active", "virtual": False, "is_subagent": False, "controller_ids": ["ctrl-a"], "progress_measurement": {"total_units": 4, "completed_units": 4, "basis": "caller", "observed_at_ms": 1}},
            {"id": "subagent", "project_id": "project:a", "role": "doer", "status": "done", "virtual": False, "is_subagent": True, "controller_ids": ["ctrl-a"]},
        ]
        summary = console.App._progress_for_nodes(nodes, {"type": "ctrl", "ctrl_id": "ctrl-a", "project_id": "project:a"})
        self.assertEqual(summary["counts"], {"tasks": 3, "completed": 1, "blocked": 1})
        self.assertEqual(summary["tasks"][0]["latest_proof_receipt"], "proof-1")
        self.assertEqual(summary["tasks"][1]["blocker"], "Dependency is not complete.")
        self.assertIsNone(summary["tasks"][2]["progress"])
        self.assertIsNone(summary["progress"])
        self.assertEqual(summary["progress_display"], "Unmeasured")
        self.assertIn("status, token volume, elapsed time", summary["claim_limit"])

    def test_console_usage_route_is_read_only_and_has_no_host_mutation_authority(self) -> None:
        source = SERVER.read_text(encoding="utf-8")
        self.assertIn('if path == "/api/usage-history":', source)
        self.assertIn('query["target_reset_at_ms"]', source)
        self.assertIn('query["remaining_token_budget"]', source)
        self.assertNotIn('query["token_limit"]', source)
        self.assertIn('if path == "/api/progress":', source)
        for rejected in ("USER_CUSTODY_OPERATIONS", "prepare_user_mutation", "user_custody_receipts"):
            self.assertNotIn(rejected, source)

    def test_eta_heartbeat_without_task_owner_report_never_creates_forecast(self) -> None:
        path = self.root / "console" / "eta.sqlite3"
        now = int(time.time() * 1000)
        overview = {
            "heartbeat_minutes": 1,
            "nodes": [{
                "id": "quiet-task", "project_id": "project:alpha", "tokens": 2,
                "status": "quiet", "updated_at": now - 120_000,
            }],
            "links": [],
        }
        store = console.ConsoleStore(path)
        store.observe_overview(overview, now_ms=now, trigger="startup", heartbeat_minutes=1)
        store.observe_overview(overview, now_ms=now + 61_000, trigger="heartbeat", heartbeat_minutes=1)
        self.assertEqual(store.latest_forecasts(), {})

    def test_elapsed_time_and_token_volume_never_create_eta(self) -> None:
        store = console.ConsoleStore(self.root / "console" / "eta-signals.sqlite3")
        now = int(time.time() * 1000)
        store.observe_overview({
            "heartbeat_minutes": 30,
            "nodes": [
                {"id": "new-task", "project_id": "project:alpha", "tokens": 20, "status": "active", "created_at": now - 20 * 60_000, "updated_at": now},
                {"id": "deep-task", "project_id": "project:alpha", "tokens": 20_000, "status": "active", "created_at": now - 4 * 60 * 60_000, "updated_at": now},
            ],
            "links": [],
        }, now_ms=now, trigger="startup", heartbeat_minutes=30)
        self.assertEqual(store.latest_forecasts(), {})

    def test_read_only_console_views_do_not_observe_or_record_usage(self) -> None:
        app = console.App(self.codex_home, self.config)
        with mock.patch.object(app, "observe_once", side_effect=AssertionError("write path")):
            diagnostics = app.diagnostics()
            overview = app.overview()
        self.assertFalse(diagnostics["usage_consumed"])
        self.assertNotIn("tokens", diagnostics)
        self.assertIn("token_history", overview)

    def test_clear_history_does_not_delete_ctrl_overlays(self) -> None:
        store = console.ConsoleStore(self.root / "console" / "scoped.sqlite3")
        now = int(time.time() * 1000)
        store.update_ctrl_override("ctrl-1", {"reasoning": "high"}, expected_revision=0, now_ms=now)
        store.observe_overview({
            "heartbeat_minutes": 30,
            "nodes": [{"id": "task-1", "project_id": "project:alpha", "tokens": 3, "status": "active", "updated_at": now}],
            "links": [],
        }, now_ms=now, trigger="startup", heartbeat_minutes=30)
        result = store.clear_history()
        self.assertTrue(result["ok"])
        self.assertEqual(store.get_ctrl_override("ctrl-1")["revision"], 1)
        self.assertEqual(store.storage_stats()["counts"]["token_samples"], 0)

    def test_proof_feed_exposes_available_media_without_fabricating_surface(self) -> None:
        media_path = self.root / "proof.png"
        media_path.write_bytes(b"\x89PNG\r\n\x1a\nproof")
        store = console.ConsoleStore(self.root / "console" / "proof.sqlite3")
        base = {
            "source": "CtrlEvidence", "evidence_id": "evidence-1", "task_id": "task-1",
            "project_id": "project:alpha", "kind": "screenshot", "locator": str(media_path),
            "caption": "Screenshot proof", "claim_limit": "Local screenshot only.",
            "receipt": "proof-event:evidence-1", "surface_kind": "available_media",
        }
        item = store.record_proof_media({**base, "disposition": "PENDING"}, now_ms=1)
        self.assertEqual(item["evidence_id"], "evidence-1")
        feed_item = store.proof_feed(project_id="project:alpha")[0]
        self.assertEqual(feed_item["media_type"], "image/png")
        self.assertEqual(feed_item["disposition"], "PENDING")
        self.assertNotIn("locator", feed_item)
        self.assertEqual(store.proof_sequence(), 1)
        with self.assertRaises(console.ConsoleError):
            store.record_proof_media({**base, "disposition": "SURFACED"}, now_ms=2)
        with self.assertRaises(console.ConsoleError):
            store.record_proof_media({**base, "caption": "Changed", "disposition": "PENDING"}, now_ms=3)
        with self.assertRaisesRegex(console.ConsoleError, "plain project language"):
            store.record_proof_media({**base, "evidence_id": "internal-copy", "caption": "Localhost proof", "disposition": "PENDING"}, now_ms=4)

    def test_proof_cursor_is_monotonic_and_detects_same_timestamp_media(self) -> None:
        first_path = self.root / "same-ms-first.png"
        second_path = self.root / "same-ms-second.png"
        first_path.write_bytes(b"\x89PNG\r\n\x1a\nfirst")
        second_path.write_bytes(b"\x89PNG\r\n\x1a\nsecond")
        store = console.ConsoleStore(self.root / "console" / "same-ms-proof.sqlite3")

        def payload(evidence_id: str, locator: Path) -> dict[str, str]:
            return {
                "source": "CtrlEvidence", "evidence_id": evidence_id, "task_id": "task-1",
                "project_id": "project:alpha", "kind": "screenshot", "locator": str(locator),
                "caption": f"Proof {evidence_id}", "claim_limit": "Local screenshot only.",
                "receipt": f"proof-event:{evidence_id}", "disposition": "PENDING",
            }

        store.record_proof_media(payload("same-ms-first", first_path), now_ms=77)
        first_cursor = store.proof_cursor()
        self.assertEqual(first_cursor["sequence"], 1)
        self.assertEqual(store.proof_cursor(), first_cursor)
        store.record_proof_media(payload("same-ms-second", second_path), now_ms=77)
        second_cursor = store.proof_cursor()
        self.assertEqual(second_cursor["sequence"], 2)
        self.assertNotEqual(second_cursor["identity"], first_cursor["identity"])
        self.assertEqual(store.proof_sequence(), second_cursor["sequence"])

    def test_assets_generation_is_durable_typed_and_cursor_bound(self) -> None:
        app = console.App(self.codex_home, self.config)
        payload = self._asset_generation_payload()
        reserved = app.accept_asset_generation(payload)
        asset = reserved["asset"]
        self.assertEqual(asset["presentation"]["status"], "queued")
        self.assertEqual(asset["technical"]["revision"], 1)
        self.assertEqual(asset["technical"]["created_at_ms"], asset["technical"]["updated_at_ms"])
        self.assertEqual(asset["preview"]["state"], "NOT_READY")
        self.assertIsNone(asset["preview"]["url"])
        self.assertIsNone(asset["technical"]["storage"]["path"])
        self.assertNotIn("locator", json.dumps(asset))
        self.assertEqual(asset["event_cursor"]["sequence"], 1)

        replay = app.accept_asset_generation(payload)
        self.assertEqual(replay["asset"]["event_cursor"], asset["event_cursor"])
        self.assertEqual(len(app.asset_event_projection(project_id="project:alpha")["items"]), 1)

        generating = app.advance_asset_generation({
            "project_id": "project:alpha", "asset_id": "asset-dashboard-a",
            "expected_revision": 1, "operation_id": "generation-op-a", "status": "generating",
        })["asset"]
        self.assertEqual(generating["presentation"]["status"], "generating")
        self.assertIsNone(generating["technical"]["measured_progress"])
        generating_progress = app.advance_asset_generation({
            "project_id": "project:alpha", "asset_id": "asset-dashboard-a",
            "expected_revision": 2, "operation_id": "generation-op-a", "status": "generating",
            "measured_progress": 0.2, "measured_progress_provenance": "runtime-receipt-progress-a",
        })["asset"]
        self.assertEqual(generating_progress["technical"]["revision"], 3)
        self.assertEqual(generating_progress["technical"]["measured_progress"], 0.2)
        validating = app.advance_asset_generation({
            "project_id": "project:alpha", "asset_id": "asset-dashboard-a",
            "expected_revision": 3, "operation_id": "generation-op-a", "status": "validating",
            "measured_progress": 0.35, "measured_progress_provenance": "runtime-receipt-a",
        })["asset"]
        self.assertEqual(validating["technical"]["measured_progress"], 0.35)
        self.assertEqual(validating["technical"]["measured_progress_provenance"], "runtime-receipt-a")

        media_root = self.codex_home / console.PROOF_MEDIA_ROOT
        media_root.mkdir(parents=True)
        media_path = media_root / "dashboard-a.png"
        media_path.write_bytes(b"\x89PNG\r\n\x1a\nasset-dashboard-a")
        digest = hashlib.sha256(media_path.read_bytes()).hexdigest()
        ready = app.admit_asset_file({
            "project_id": "project:alpha", "asset_id": "asset-dashboard-a",
            "expected_revision": 4, "operation_id": "generation-op-a", "locator": str(media_path),
            "digest": digest,
            "provenance": {"source": "runtime", "receipt": "file-receipt-a", "admission": "admit-a"},
        })["asset"]
        self.assertEqual(ready["presentation"]["status"], "ready")
        self.assertEqual(ready["technical"]["digest"], digest)
        self.assertEqual(ready["preview"]["state"], "AVAILABLE")
        self.assertIn("/api/assets/asset-dashboard-a/preview?digest=", ready["preview"]["url"])
        self.assertNotIn(str(media_path), json.dumps(ready))

        events = app.asset_event_projection(project_id="project:alpha")
        self.assertEqual(events["status"], "available")
        self.assertEqual([item["to_status"] for item in events["items"]], ["queued", "generating", "generating", "validating", "ready"])
        self.assertEqual(events["cursor"], ready["event_cursor"])
        self.assertEqual(len({item["cursor"]["identity"] for item in events["items"]}), 5)
        self.assertEqual(len(app.assets_projection(project_id="all")["items"]), 1)
        self.assertEqual(app.asset_event_projection(project_id="all")["status"], "available")

        restarted = console.App(self.codex_home, self.config, state_path=app.store.path)
        retained = restarted.asset_detail("asset-dashboard-a", project_id="project:alpha")["asset"]
        self.assertEqual(retained["technical"]["revision"], 5)
        self.assertEqual(retained["preview"]["state"], "AVAILABLE")
        self.assertEqual(retained["event_cursor"], ready["event_cursor"])

    def test_assets_keep_options_distinct_and_trash_is_reversible(self) -> None:
        app = console.App(self.codex_home, self.config)
        first = app.accept_asset_generation(self._asset_generation_payload())["asset"]
        with self.assertRaisesRegex(console.ConsoleError, "requested logical asset"):
            app.accept_asset_generation(self._asset_generation_payload(
                "asset-dashboard-invalid-lineage", logical_asset_id="logical-other",
                operation_id="generation-op-invalid-lineage", generation_job_id="generation-job-invalid-lineage",
                idempotency_key="generation-request-invalid-lineage", parent_revision_id="asset-dashboard-a",
            ))
        second = app.accept_asset_generation(self._asset_generation_payload(
            "asset-dashboard-b", operation_id="generation-op-b", generation_job_id="generation-job-b",
            idempotency_key="generation-request-b", parent_revision_id="asset-dashboard-a",
        ))["asset"]
        self.assertNotEqual(first["asset_id"], second["asset_id"])
        self.assertEqual(second["technical"]["logical_asset_id"], first["technical"]["logical_asset_id"])
        self.assertEqual(second["technical"]["parent_revision_id"], first["asset_id"])
        self.assertEqual(len(app.assets_projection(project_id="project:alpha")["items"]), 2)

        trashed = app.trash_asset({
            "project_id": "project:alpha", "asset_id": "asset-dashboard-a", "expected_revision": 1,
            "operation_id": "trash-dashboard-a", "trashed_by": "user",
        })["asset"]
        self.assertTrue(trashed["trash"]["trashed"])
        self.assertIsNotNone(trashed["trash"]["trashed_at"])
        self.assertEqual(trashed["trash"]["trashed_by"], "user")
        self.assertEqual(len(app.assets_projection(project_id="project:alpha")["items"]), 1)
        self.assertEqual(len(app.assets_projection(project_id="project:alpha", projection="trash")["items"]), 1)
        replay = app.trash_asset({
            "project_id": "project:alpha", "asset_id": "asset-dashboard-a", "expected_revision": 1,
            "operation_id": "trash-dashboard-a", "trashed_by": "user",
        })["asset"]
        self.assertEqual(replay["technical"]["revision"], trashed["technical"]["revision"])
        restored = app.restore_asset({
            "project_id": "project:alpha", "asset_id": "asset-dashboard-a", "expected_revision": 2,
            "operation_id": "restore-dashboard-a", "restored_by": "user",
        })["asset"]
        self.assertFalse(restored["trash"]["trashed"])
        self.assertEqual(len(app.assets_projection(project_id="project:alpha")["items"]), 2)
        with self.assertRaisesRegex(console.ConsoleError, "manual/unconfigured"):
            app.purge_assets(project_id="project:alpha")

    def test_assets_fail_retry_cancel_and_reject_stale_generation_events(self) -> None:
        app = console.App(self.codex_home, self.config)
        reserved = app.accept_asset_generation(self._asset_generation_payload(
            "asset-retry", logical_asset_id="logical-retry", operation_id="op-retry-1",
            generation_job_id="job-retry-1", idempotency_key="request-retry",
        ))["asset"]
        generating = app.advance_asset_generation({
            "project_id": "project:alpha", "asset_id": "asset-retry", "expected_revision": 1,
            "operation_id": "op-retry-1", "status": "generating",
        })["asset"]
        failed = app.fail_asset_generation({
            "project_id": "project:alpha", "asset_id": "asset-retry", "expected_revision": 2,
            "operation_id": "op-retry-1", "error_class": "RUNTIME_UNAVAILABLE", "retry_eligible": True,
        })["asset"]
        self.assertEqual(failed["presentation"]["status"], "failed")
        self.assertTrue(failed["technical"]["retry_eligible"])
        retried = app.retry_asset_generation({
            "project_id": "project:alpha", "asset_id": "asset-retry", "expected_revision": 3,
            "operation_id": "op-retry-2", "generation_job_id": "job-retry-2",
        })["asset"]
        self.assertEqual(retried["presentation"]["status"], "queued")
        self.assertEqual(retried["technical"]["operation_id"], "op-retry-2")
        self.assertEqual(retried["technical"]["logical_asset_id"], reserved["technical"]["logical_asset_id"])
        self.assertEqual(retried["technical"]["parent_revision_id"], reserved["technical"]["parent_revision_id"])
        with self.assertRaises(console.ConsoleConflict):
            app.advance_asset_generation({
                "project_id": "project:alpha", "asset_id": "asset-retry", "expected_revision": 3,
                "operation_id": "op-retry-1", "status": "generating",
            })
        cancelled = app.cancel_asset_generation({
            "project_id": "project:alpha", "asset_id": "asset-retry", "expected_revision": 4,
            "operation_id": "cancel-retry",
        })["asset"]
        self.assertEqual(cancelled["presentation"]["status"], "cancelled")
        self.assertEqual(app.asset_event_projection(project_id="project:alpha")["items"][-1]["to_status"], "cancelled")

    def test_assets_fail_closed_for_file_provenance_and_missing_files(self) -> None:
        app = console.App(self.codex_home, self.config)
        app.accept_asset_generation(self._asset_generation_payload(
            "asset-file-guard", logical_asset_id="logical-file-guard", operation_id="op-file-guard",
            generation_job_id="job-file-guard", idempotency_key="request-file-guard",
        ))
        app.advance_asset_generation({
            "project_id": "project:alpha", "asset_id": "asset-file-guard", "expected_revision": 1,
            "operation_id": "op-file-guard", "status": "generating",
        })
        app.advance_asset_generation({
            "project_id": "project:alpha", "asset_id": "asset-file-guard", "expected_revision": 2,
            "operation_id": "op-file-guard", "status": "validating",
        })
        outside = self.root / "outside.png"
        outside.write_bytes(b"\x89PNG\r\n\x1a\noutside")
        outside_digest = hashlib.sha256(outside.read_bytes()).hexdigest()
        with self.assertRaisesRegex(console.ConsoleError, "file admission failed closed"):
            app.admit_asset_file({
                "project_id": "project:alpha", "asset_id": "asset-file-guard", "expected_revision": 3,
                "operation_id": "op-file-guard", "locator": str(outside), "digest": outside_digest,
                "provenance": {"source": "runtime", "receipt": "file-guard", "admission": "guard"},
            })
        with self.assertRaisesRegex(console.ConsoleError, "admission receipt"):
            app.admit_asset_file({
                "project_id": "project:alpha", "asset_id": "asset-file-guard", "expected_revision": 3,
                "operation_id": "op-file-guard", "locator": str(outside), "digest": outside_digest,
                "provenance": {"source": "runtime", "receipt": "file-guard"},
            })
        media_root = self.codex_home / console.PROOF_MEDIA_ROOT
        media_root.mkdir(parents=True)
        media_path = media_root / "file-guard.png"
        media_path.write_bytes(b"\x89PNG\r\n\x1a\nfile-guard")
        digest = hashlib.sha256(media_path.read_bytes()).hexdigest()
        ready = app.admit_asset_file({
            "project_id": "project:alpha", "asset_id": "asset-file-guard", "expected_revision": 3,
            "operation_id": "op-file-guard", "locator": str(media_path), "digest": digest,
            "provenance": {"source": "runtime", "receipt": "file-ready", "admission": "guard-ready"},
        })["asset"]
        self.assertEqual(ready["preview"]["state"], "AVAILABLE")
        media_path.unlink()
        missing = app.asset_detail("asset-file-guard", project_id="project:alpha")["asset"]
        self.assertEqual(missing["preview"]["state"], "UNAVAILABLE")
        self.assertIsNone(missing["preview"]["url"])
        self.assertEqual(missing["technical"]["storage"]["state"], "UNAVAILABLE")

    def test_store_migration_normalizes_available_rows_but_preserves_withheld(self) -> None:
        media_path = self.root / "legacy.png"
        media_path.write_bytes(b"\x89PNG\r\n\x1a\nlegacy")
        database = self.root / "console" / "legacy.sqlite3"
        store = console.ConsoleStore(database)
        item = store.record_proof_media({
            "source": "CtrlEvidence", "evidence_id": "legacy-proof", "task_id": "task-1",
            "project_id": "project:alpha", "kind": "screenshot", "locator": str(media_path),
            "caption": "Legacy proof", "claim_limit": "Available for review.",
            "receipt": "legacy:caller", "disposition": "PENDING",
        }, now_ms=1)
        connection = sqlite3.connect(database)
        try:
            connection.execute("UPDATE proof_media SET disposition='SURFACED', surface_kind='inline_image' WHERE evidence_id='legacy-proof'")
            connection.execute(
                "INSERT INTO proof_media(evidence_id, task_id, project_id, kind, locator, caption, claim_limit, disposition, receipt, surface_kind, media_type, mtime_ns, size_bytes, digest, registered_at_ms, updated_at_ms) "
                "SELECT 'available-proof', task_id, project_id, kind, locator, 'Available proof', claim_limit, 'AVAILABLE', 'legacy:available', 'available_media', media_type, mtime_ns, size_bytes, digest, registered_at_ms, updated_at_ms FROM proof_media WHERE evidence_id='legacy-proof'"
            )
            connection.execute(
                "INSERT INTO proof_media(evidence_id, task_id, project_id, kind, locator, caption, claim_limit, disposition, receipt, surface_kind, media_type, mtime_ns, size_bytes, digest, registered_at_ms, updated_at_ms) "
                "SELECT 'withheld-proof', task_id, project_id, kind, locator, 'Withheld proof', claim_limit, 'WITHHELD', 'ctrl:withheld', 'withheld', media_type, mtime_ns, size_bytes, digest, registered_at_ms, updated_at_ms FROM proof_media WHERE evidence_id='legacy-proof'"
            )
            connection.commit()
        finally:
            connection.close()
        migrated = {entry["evidence_id"]: entry for entry in console.ConsoleStore(database).proof_feed()}
        self.assertEqual(migrated["legacy-proof"]["evidence_id"], item["evidence_id"])
        self.assertEqual(migrated["legacy-proof"]["disposition"], "PENDING")
        self.assertEqual(migrated["legacy-proof"]["surface_kind"], "available_media")
        self.assertEqual(migrated["available-proof"]["disposition"], "PENDING")
        self.assertEqual(migrated["available-proof"]["surface_kind"], "available_media")
        connection = sqlite3.connect(database)
        try:
            withheld = connection.execute(
                "SELECT disposition, receipt, surface_kind FROM proof_media WHERE evidence_id='withheld-proof'"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(withheld, ("WITHHELD", "ctrl:withheld", "withheld"))
        self.assertNotIn("withheld-proof", {item["evidence_id"] for item in console.ConsoleStore(database).proof_feed()})

    def test_project_view_scopes_burn_history_and_navigation(self) -> None:
        app = console.App(self.codex_home, self.config)
        overview = {
            "nodes": [
                {"id": "ctrl-a", "project_id": "project:a", "role": "ctrl", "status": "active", "virtual": False, "tokens": 10},
                {"id": "task-a", "project_id": "project:a", "role": "doer", "status": "active", "virtual": False, "tokens": 20},
                {"id": "ctrl-b", "project_id": "project:b", "role": "ctrl", "status": "active", "virtual": False, "tokens": 30},
            ],
            "links": [],
            "roots": ["ctrl-a", "ctrl-b"],
            "controllers": [
                {"id": "ctrl-a", "project_id": "project:a", "title": "CTRL - Alpha", "status": "active", "updated_at": 2, "archived": False, "archive_source": "host_threads.archived", "controller_classification": "swarm_ctrl", "controller_classification_source": "host_threads.agent_role"},
                {"id": "ctrl-b", "project_id": "project:b", "title": "CTRL - Beta", "status": "active", "updated_at": 1, "archived": False, "archive_source": "host_threads.archived", "controller_classification": "swarm_ctrl", "controller_classification_source": "host_threads.agent_role"},
            ],
            "projects": [
                {"id": "project:a", "name": "Alpha", "goal_label": "Alpha goal", "label_source": "working_directory"},
                {"id": "project:b", "name": "Beta", "goal_label": "Beta goal", "label_source": "working_directory"},
            ],
            "analytics": {"swarms": 2},
        }
        with mock.patch.object(app.store, "token_history", return_value=[{"bucket_ms": 1, "delta_tokens": 7, "source": "host_reported_cumulative_delta"}]) as history:
            view = app._project_view(overview, "project:a")
        history.assert_called_once_with(project_id="project:a")
        self.assertEqual(view["token_history"][0]["delta_tokens"], 7)
        self.assertEqual(view["analytics"]["burn_rate"]["history"][0]["delta_tokens"], 7)
        self.assertEqual(view["navigation"]["active_ctrl_id"], "ctrl-a")
        self.assertEqual(
            [project["id"] for project in view["navigation"]["projects"]],
            ["project:a", "project:b"],
        )
        alpha = next(project for project in view["navigation"]["projects"] if project["id"] == "project:a")
        beta = next(project for project in view["navigation"]["projects"] if project["id"] == "project:b")
        self.assertEqual(alpha["goal_label"], "Alpha goal")
        self.assertEqual(alpha["task_count"], 2)
        self.assertEqual(beta["task_count"], 1)

    def test_navigation_eligibility_uses_persisted_ctrl_and_archive_authority(self) -> None:
        now = int(time.time() * 1000)
        quiet = now - 2 * 60 * 60 * 1000
        for name in ("idle", "stalled", "archived", "legacy", "noctrl"):
            self._add_host_project(f"project:{name}", name, f"C:/work/{name}")
        connection = sqlite3.connect(self.database)
        connection.execute("UPDATE threads SET agent_role='ctrl' WHERE id='root'")
        rows = [
            ("ctrl-idle", "🐙CTRL - Idle", "C:/work/idle", quiet, quiet, 0, "ctrl"),
            ("ctrl-stalled", "🐙CTRL - Stalled", "C:/work/stalled", quiet, quiet, 0, "ctrl"),
            ("ctrl-archived", "🐙CTRL - Archived", "C:/work/archived", now, now, 1, "ctrl"),
            ("legacy-title", "🐙CTRL - Legacy", "C:/work/legacy", now, now, 0, ""),
            ("no-ctrl", "🔨DEV - Standalone", "C:/work/noctrl", now, now, 0, "doer"),
        ]
        for thread_id, title, cwd, created, updated, archived, agent_role in rows:
            connection.execute(
                "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (thread_id, title, cwd, created // 1000, updated // 1000, created, updated,
                 "gpt-5.6-luna", "high", 0, archived, "", "main", "", "", agent_role, 0),
            )
        connection.commit()
        connection.close()

        production = console.build_overview(self.codex_home, self.config)
        stalled_controller = next(
            item for item in production["controllers"] if item["id"] == "ctrl-stalled"
        )
        stalled_controller["status"] = "blocked"
        navigation = console.App._navigation_payload(production)
        project_ids = {project["name"]: project["id"] for project in production["projects"]}
        by_project = {item["id"]: item for item in navigation["projects"]}
        by_controller = {item["id"]: item for item in navigation["controllers"]}
        idle = by_project[project_ids["idle"]]
        stalled = by_project[project_ids["stalled"]]
        archived = by_project[project_ids["archived"]]
        legacy = by_project[project_ids["legacy"]]
        no_ctrl = by_project[project_ids["noctrl"]]
        self.assertEqual(idle["project_eligibility"], "swarm_ctrl")
        self.assertEqual(idle["ctrl_ids"], ["ctrl-idle"])
        self.assertEqual(stalled["project_eligibility"], "swarm_ctrl")
        self.assertEqual(stalled["ctrl_ids"], ["ctrl-stalled"])
        self.assertEqual(no_ctrl["project_eligibility"], "host_tasks")
        self.assertFalse(no_ctrl["archived"])
        self.assertEqual(archived["visibility"], "visible")
        self.assertFalse(archived["archived"])
        self.assertEqual(archived["archive_source"], "host_projects")
        self.assertEqual(archived["project_eligibility"], "no_ctrl")
        self.assertEqual(legacy["project_eligibility"], "host_tasks")
        self.assertEqual(legacy["eligibility_source"], "unavailable")
        self.assertEqual(legacy["ctrl_ids"], [])
        self.assertEqual(by_controller["ctrl-idle"]["controller_classification"], "swarm_ctrl")
        self.assertEqual(by_controller["ctrl-idle"]["visibility"], "visible")
        self.assertNotIn("ctrl-archived", by_controller)
        self.assertEqual(by_controller["legacy-title"]["controller_classification"], "unavailable")
        self.assertEqual(by_controller["legacy-title"]["visibility"], "hidden")
        self.assertNotIn("ctrl-archived", navigation["active_ctrl_ids"])

    def test_overview_metrics_share_one_cursor_and_fail_closed_without_receipts(self) -> None:
        app = console.App(self.codex_home, self.config, self.root / "console" / "metrics.sqlite3")
        first = app.overview()["overview_metrics"]
        second = app.overview()["overview_metrics"]
        self.assertEqual(first, second)
        self.assertEqual(first["accepted_scope_id"], "all")
        self.assertEqual(first["accepted_cursor"]["type"], "overview_metrics_v1")
        self.assertEqual(set(first["field_state"]), set(console.OVERVIEW_METRIC_FIELDS))
        self.assertEqual(first["field_state"]["remaining_tokens"], "UNKNOWN")
        self.assertIsNone(first["usage"]["remaining_tokens"])
        self.assertEqual(first["field_state"]["admitted_proof"], "UNKNOWN")
        self.assertIsNone(first["verified_progress"]["admitted_proof"])
        self.assertNotEqual(first["accepted_cursor"]["digest"], "0" * 64)

    def test_overview_metrics_invalid_retained_weight_stays_unknown(self) -> None:
        app = console.App(self.codex_home, self.config, self.root / "console" / "invalid-metrics.sqlite3")
        view = console.build_overview(self.codex_home, self.config)
        view["navigation"] = console.App._navigation_payload(view)
        view["token_history"] = []
        invalid_projection = {
            "cursor": {"event_seq": 1},
            "scopes": {"project:alpha": 1},
            "blocks": {
                "invalid": {
                    "project_id": "project:alpha", "ctrl_id": "root", "block_id": "invalid",
                    "scope_version": 1, "lifecycle_state": "ACTIVE", "flags": [],
                    "observed_at_ms": 1, "admitted_proof_weight": None, "committed_weight": 1,
                },
            },
        }
        with mock.patch.object(app.progress_ledger, "replay", return_value=invalid_projection) as replay:
            metrics = app._overview_metrics(view, scope_id="all")
        self.assertEqual(replay.call_count, 1)
        self.assertEqual(metrics["field_state"]["admitted_proof"], "UNKNOWN")
        self.assertIsNone(metrics["verified_progress"]["admitted_proof"])

    def test_overview_metrics_use_one_ledger_projection_for_known_progress_and_attention(self) -> None:
        self._confirm_root_ctrl()
        app = console.App(self.codex_home, self.config, self.root / "console" / "known-metrics.sqlite3")
        self._append_notification_fixture(app)
        metrics = app.overview()["overview_metrics"]
        self.assertEqual(metrics["accepted_scope_id"], metrics["accepted_cursor"]["scope_id"])
        self.assertEqual(metrics["active_work"]["active_projects"], 1)
        self.assertEqual(metrics["active_work"]["active_lanes"], 0)
        self.assertEqual(metrics["field_state"]["actionable_items"], "KNOWN")
        self.assertGreater(metrics["needs_attention"]["actionable_items"], 0)
        self.assertEqual(metrics["field_state"]["total"], "KNOWN")
        self.assertGreater(metrics["verified_progress"]["total"], 0)
        self.assertIn(metrics["field_state"]["percent"], {"KNOWN", "PARTIAL", "UNKNOWN"})

    def test_overview_metrics_match_navigation_current_work_inventory(self) -> None:
        self._confirm_root_ctrl()
        self._add_host_project("project:archived", "archived", "C:/work/archived")
        self._add_host_project("project:legacy", "legacy", "C:/work/legacy")
        now = 2_000_000_100_000
        with closing(sqlite3.connect(self.database)) as connection:
            connection.executemany(
                "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        "archived-ctrl", "🐙CTRL - Archived", "C:/work/archived", now // 1000,
                        now // 1000, now, now, "gpt-5.6-sol", "high", 1, 1, "", "main",
                        "", "", "ctrl", 0,
                    ),
                    (
                        "legacy-ctrl", "🐙CTRL - Legacy", "C:/work/legacy", now // 1000,
                        now // 1000, now, now, "gpt-5.6-sol", "high", 1, 0, "", "main",
                        "", "", "", 0,
                    ),
                ],
            )
            connection.commit()

        app = console.App(self.codex_home, self.config, self.root / "console" / "filtered-metrics.sqlite3")
        view = app.overview()
        metrics = view["overview_metrics"]
        navigation = view["navigation"]
        self.assertEqual(metrics["active_work"], {"active_projects": 2, "active_lanes": 0})
        self.assertEqual(metrics["field_state"]["active_projects"], "KNOWN")
        self.assertEqual(metrics["field_state"]["active_lanes"], "KNOWN")
        self.assertNotIn("archived-ctrl", navigation["active_ctrl_ids"])
        self.assertNotIn("legacy-ctrl", navigation["active_ctrl_ids"])

    def test_missing_canonical_project_inventory_is_unknown_not_zero(self) -> None:
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DROP TABLE projects")
            connection.commit()

        app = console.App(self.codex_home, self.config, self.root / "console" / "missing-projects.sqlite3")
        view = app.overview()
        metrics = view["overview_metrics"]
        self.assertEqual(view["project_inventory"]["state"], "UNKNOWN")
        self.assertFalse(view["project_inventory"]["available"])
        self.assertEqual(view["navigation"]["project_inventory"]["state"], "UNKNOWN")
        self.assertIsNone(metrics["active_work"]["active_projects"])
        self.assertIsNone(metrics["active_work"]["active_lanes"])
        self.assertEqual(metrics["field_state"]["active_projects"], "UNKNOWN")
        self.assertEqual(metrics["field_state"]["active_lanes"], "UNKNOWN")
        roster = app.project_roster()
        self.assertEqual(roster["state"], "UNKNOWN")
        self.assertFalse(roster["available"])
        self.assertEqual(roster["projects"], [])
        scoped = app._project_view(view, "project:alpha")
        self.assertEqual(scoped["navigation"]["project_inventory"]["state"], "UNKNOWN")
        self.assertEqual(scoped["navigation"]["projects"], [])

    def test_navigation_is_saved_project_feed_with_status_facts_and_stable_inputs(self) -> None:
        self._add_host_project("project:empty", "Empty saved project", "C:/work/empty")
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE projects SET position=4 WHERE id='project:alpha'")
            connection.execute("UPDATE projects SET position=1 WHERE id='project:empty'")
            connection.commit()
        overview = console.build_overview(self.codex_home, self.config)
        navigation = console.App._navigation_payload(overview)
        self.assertEqual(
            [project["id"] for project in navigation["projects"][:2]],
            ["project:empty", "project:alpha"],
        )
        saved = next(project for project in navigation["projects"] if project["id"] == "project:empty")
        self.assertEqual(saved["status"], "inactive")
        self.assertEqual(saved["status_facts"], {
            "active": False,
            "stalled": False,
            "inactive": True,
            "source": "host manifest admission+host_threads.archived+host_threads.updated_at_ms",
        })
        self.assertEqual(saved["active_ctrl"], False)
        self.assertEqual(saved["ordering"]["position"], 1)
        self.assertNotIn("task", {project["id"] for project in navigation["projects"]})
        self.assertNotIn("C:/work/alpha", json.dumps(navigation["projects"]))

    def test_project_roster_enumerates_saved_projects_and_keeps_current_work_separate(self) -> None:
        self._confirm_root_ctrl()
        inactive_root = self.root / "inactive-project"
        inactive_root.mkdir()
        self._add_host_project("project:inactive", "inactive", str(inactive_root))

        app = console.App(self.codex_home, self.config, self.root / "console" / "project-roster.sqlite3")
        roster = app.project_roster()
        self.assertTrue(roster["ok"])
        self.assertEqual(roster["state"], "KNOWN")
        self.assertTrue(roster["available"])
        self.assertEqual(
            {project["id"] for project in roster["projects"]},
            {"project:alpha", "project:inactive"},
        )
        self.assertNotIn("task", {project["id"] for project in roster["projects"]})

        alpha = next(project for project in roster["projects"] if project["id"] == "project:alpha")
        inactive = next(project for project in roster["projects"] if project["id"] == "project:inactive")
        self.assertEqual(alpha["display_name"], "alpha")
        self.assertEqual(alpha["root"], "C:/work/alpha")
        self.assertEqual(alpha["root_status"], "KNOWN")
        self.assertEqual(alpha["status"], "active")
        self.assertEqual(inactive["status"], "inactive")
        self.assertEqual(inactive["status_facts"]["inactive"], True)
        self.assertFalse(inactive["current_work"])
        self.assertTrue(alpha["current_work"])
        self.assertEqual(roster["current_work"]["state"], "KNOWN")
        self.assertEqual(roster["current_work"]["project_ids"], ["project:alpha"])
        self.assertEqual(
            [project["id"] for project in roster["current_work"]["projects"]],
            ["project:alpha"],
        )
        self.assertEqual(roster["cursor"]["type"], "codex_project_roster_v1")
        source = SERVER.read_text(encoding="utf-8")
        self.assertIn('if path == "/api/projects":', source)
        self.assertIn('if path == "/api/projects/settings":', source)

    def test_project_roster_reuses_the_observer_snapshot(self) -> None:
        self._confirm_root_ctrl()
        app = console.App(self.codex_home, self.config, self.root / "console" / "project-roster-cache.sqlite3")
        with mock.patch.object(app, "_host_overview", wraps=app._host_overview) as overview:
            roster = app.project_roster()
        self.assertEqual(roster["state"], "KNOWN")
        overview.assert_called_once_with()

    def test_daily_report_reuses_the_published_host_snapshot(self) -> None:
        app = console.App(self.codex_home, self.config, self.root / "console" / "daily-report.sqlite3")
        app._overview = {
            "generated_at": "2026-09-14T00:00:00+00:00",
            "project_inventory": {"state": "KNOWN"},
            "projects": [{"id": "project:alpha", "name": "alpha", "active": 1}],
            "nodes": [{"id": "task", "project_id": "project:alpha"}],
        }
        with mock.patch.object(app, "_host_overview", side_effect=AssertionError("must reuse snapshot")):
            report = app.daily_report()
        self.assertEqual(report["state"], "KNOWN")
        self.assertEqual(report["projects"][0]["activity_status"], "active")
        self.assertEqual(report["nodes"][0]["id"], "task")

    def test_project_roster_withholds_ambiguous_manifest_and_unknown_logo_bindings(self) -> None:
        identity_root = self.root / "identity-project"
        self._write_project_brief(identity_root, "project:identity")
        self._add_host_project("project:identity", "identity", str(identity_root))
        invalid_root = self.root / "invalid-project"
        invalid_root.mkdir()
        invalid_root.joinpath("SWARM.md").write_text("# invalid", encoding="utf-8")
        self._add_host_project("project:invalid", "invalid", str(invalid_root))

        app = console.App(self.codex_home, self.config, self.root / "console" / "identity.sqlite3")
        roster = app.project_roster()
        identity = next(project for project in roster["projects"] if project["id"] == "project:identity")
        self.assertEqual(identity["manifest"]["status"], "KNOWN")
        self.assertEqual(identity["project_view"]["status"], "ABSENT")
        self.assertFalse(identity["project_view"]["available"])
        self.assertEqual(identity["artifact"]["status"], "UNKNOWN")
        self.assertIsNone(identity["artifact"]["id"])
        self.assertEqual(identity["logo"]["status"], "UNKNOWN")
        self.assertIsNone(identity["logo"]["artifact"])

        self._add_host_project("project:identity-duplicate", "identity-duplicate", str(identity_root))
        ambiguous = next(
            project for project in app.project_roster()["projects"] if project["id"] == "project:identity"
        )
        self.assertEqual(ambiguous["root_status"], "AMBIGUOUS")
        self.assertIsNone(ambiguous["root"])
        self.assertFalse(ambiguous["project_view"]["available"])
        self.assertEqual(ambiguous["logo"]["status"], "UNKNOWN")

        invalid = next(project for project in app.project_roster()["projects"] if project["id"] == "project:invalid")
        self.assertEqual(invalid["manifest"]["status"], "INVALID")
        self.assertEqual(invalid["project_view"]["status"], "INVALID")
        self.assertFalse(invalid["project_view"]["available"])
        self.assertEqual(invalid["artifact"]["status"], "UNKNOWN")

    def test_project_roster_reports_only_digest_bound_project_view_artifact(self) -> None:
        root = self.root / "known-view"
        bundle = self._write_local_project_view_bundle("project:known-view", root)
        self._add_host_project("project:known-view", "known-view", str(root))
        self._write_project_brief(root, "project:known-view", links=bundle["link"]["links"])
        sources = {
            bundle["link"]["links"][0]["ref"]: root.joinpath("ui", "swarm.project_views.json").read_bytes(),
            "project://known-view/ui/coverage.json": root.joinpath("ui", "coverage.json").read_bytes(),
            "project://known-view/ui/app-flow.mmd": root.joinpath("ui", "app-flow.mmd").read_bytes(),
        }
        app = console.App(
            self.codex_home,
            self.config,
            self.root / "console" / "known-view.sqlite3",
            project_view_resolver=lambda _project_id, ref, _digest: sources[ref],
        )
        project = next(item for item in app.project_roster()["projects"] if item["id"] == "project:known-view")
        self.assertEqual(project["manifest"]["status"], "KNOWN")
        self.assertTrue(project["project_view"]["available"])
        self.assertEqual(project["project_view"]["status"], "KNOWN")
        self.assertEqual(project["artifact"]["status"], "KNOWN")
        self.assertEqual(project["artifact"]["kind"], "swarm.project_views")
        self.assertEqual(project["artifact"]["id"], "known-view-project-views")
        self.assertEqual(project["artifact"]["version"], 18)
        self.assertEqual(
            project["artifact"]["digest"],
            project["project_view"]["identity"]["manifest_digest"],
        )
        self.assertEqual(project["logo"]["status"], "UNKNOWN")

    def test_project_settings_bind_existing_overlay_to_saved_project_cursor(self) -> None:
        app = console.App(self.codex_home, self.config, self.root / "console" / "project-settings.sqlite3")
        settings = app.project_settings("project:alpha")
        self.assertEqual(settings["scope"]["type"], "project")
        self.assertEqual(settings["scope"]["project_id"], "project:alpha")
        self.assertEqual(settings["revision"], 0)
        self.assertEqual(set(settings["editable_fields"]), console.PROJECT_SETTING_FIELDS)
        cursor = settings["accepted_cursor"]

        with self.assertRaisesRegex(console.ConsoleError, "acknowledge=true"):
            app.update_project_settings("project:alpha", {"profile": "testing"}, 0, cursor, False)
        with self.assertRaisesRegex(console.ConsoleConflict, "roster changed"):
            app.update_project_settings(
                "project:alpha", {"profile": "testing"}, 0,
                {"type": cursor["type"], "digest": "0" * 64}, True,
            )
        with self.assertRaisesRegex(console.ConsoleError, "limited to"):
            app.update_project_settings("project:alpha", {"display_name": "x"}, 0, cursor, True)

        updated = app.update_project_settings("project:alpha", {"profile": "testing"}, 0, cursor, True)
        self.assertEqual(updated["mutation_receipt"]["project_id"], "project:alpha")
        self.assertEqual(updated["mutation_receipt"]["accepted_cursor"], cursor)
        self.assertEqual(updated["revision"], 1)
        self.assertEqual(updated["overlay"]["profile"], "testing")
        self.assertEqual(updated["settings"]["profile"], "testing")
        with closing(sqlite3.connect(app.store.path)) as connection:
            row = connection.execute(
                "SELECT scope_type, scope_id, revision FROM skill_scope_overlays"
            ).fetchone()
            table_names = {
                item[0] for item in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        self.assertEqual(row, ("project", "project:alpha", 1))
        self.assertNotIn("projects", table_names)

    def test_project_create_fails_closed_without_host_capability_and_preserves_reads(self) -> None:
        app = console.App(self.codex_home, self.config, self.root / "console" / "project-create.sqlite3")
        denial = (
            "project creation is unavailable until Codex provides a host-owned capability; "
            "create the project in Codex, then refresh SWARM HQ"
        )
        roster_before = app.project_roster()
        host_before = self.database.read_bytes()
        store_before = app.store.path.read_bytes()
        ledger_path = app.progress_ledger._state.path
        ledger_before = ledger_path.read_bytes() if ledger_path.exists() else None

        with self.assertRaises(console.ConsoleError) as raised:
            app.create_project("created", str(self.root), True)
        self.assertEqual(str(raised.exception), denial)

        writer = self._handler("127.0.0.1", "127.0.0.1:4788", token=app.token)
        writer.server = SimpleNamespace(app=app)
        writer.path = "/api/projects"
        writer._payload = mock.Mock(return_value={
            "name": "created", "root": str(self.root), "acknowledge": True,
        })
        writer._json = mock.Mock()
        writer.do_POST()
        writer._json.assert_called_once_with(
            console.HTTPStatus.BAD_REQUEST, {"ok": False, "error": denial},
        )
        self.assertEqual(self.database.read_bytes(), host_before)
        self.assertEqual(app.store.path.read_bytes(), store_before)
        self.assertEqual(ledger_path.read_bytes() if ledger_path.exists() else None, ledger_before)

        reader = self._handler("127.0.0.1", "127.0.0.1:4788")
        reader.server = SimpleNamespace(app=app)
        reader.path = "/api/projects"
        reader._json = mock.Mock()
        reader.do_GET()
        reader._json.assert_called_once_with(console.HTTPStatus.OK, roster_before)

    def test_profile_presentation_is_avatar_ready_without_identity_or_secrets(self) -> None:
        app = console.App(self.codex_home, self.config, self.root / "console" / "profile.sqlite3")
        result = app.profile_presentation()
        self.assertEqual(result["state"], "KNOWN")
        self.assertEqual(result["profile"]["display_name"], "SWARM")
        avatar = result["profile"]["avatar"]
        self.assertEqual(avatar["url"], "/swarm-icon-64.png")
        self.assertEqual(avatar["media_type"], "image/png")
        self.assertEqual(
            avatar["digest"],
            hashlib.sha256((console.STATIC_ROOT / "swarm-icon-64.png").read_bytes()).hexdigest(),
        )
        serialized = json.dumps(result).casefold()
        for private in ("token", "config_path", "credential", "cookie", "prompt"):
            self.assertNotIn(f'"{private}"', serialized)

    @staticmethod
    def _project_view_requirements_fixture() -> tuple[dict[str, Any], dict[str, Any]]:
        states = ("KNOWN_SATISFIED", "PARTIAL", "MISSING", "UNKNOWN")
        group_names = ("overview", "role_library", "review", "assets", "settings", "onboarding")
        empty_bindings = {
            "accepted_artifact_refs": [], "candidate_or_observed_artifact_refs": [],
            "unregistered_artifact_refs": [], "implementation_evidence_refs": [], "browser_proof_refs": [],
        }
        shared = {
            "requirement_id": "req.shared.accessibility", "short_label": "Accessibility",
            "required": True, "target_devices": ["desktop", "tablet", "mobile"],
            "acceptance_criterion": "The surface remains operable with keyboard and touch.",
            "bindings": copy.deepcopy(empty_bindings), "derived_state": "UNKNOWN",
            "missing_target_devices": ["tablet"], "reason": "Tablet proof is not retained.",
            "applies_to_group_ids": [f"group.{name}" for name in group_names],
        }
        groups = []
        for group_index, name in enumerate(group_names):
            requirements = []
            for requirement_index in range(5):
                bindings = copy.deepcopy(empty_bindings)
                if group_index == 0 and requirement_index == 0:
                    bindings["accepted_artifact_refs"] = [{
                        "record_id": "artifact.overview", "artifact_id": "overview-approved",
                        "digest": "sha256:" + "a" * 64,
                    }]
                    bindings["implementation_evidence_refs"] = [{
                        "record_id": "evidence.overview", "artifact_id": "overview-preview",
                        "digest": "sha256:" + "b" * 64,
                    }]
                requirements.append({
                    "requirement_id": f"req.{name}.{requirement_index + 1}",
                    "short_label": f"{name.replace('_', ' ').title()} requirement {requirement_index + 1}",
                    "required": requirement_index < 4,
                    "target_devices": ["desktop", "mobile"],
                    "acceptance_criterion": "Retain exact design and implementation evidence.",
                    "bindings": bindings,
                    "derived_state": states[(group_index * 5 + requirement_index) % len(states)],
                    "missing": [] if requirement_index == 0 else ["accepted evidence"],
                    "reason": "Derived from retained immutable evidence.",
                })
            groups.append({
                "group_id": f"group.{name}", "label": name.replace("_", " ").title(),
                "order": group_index, "node_ids": [name],
                "shared_requirement_ids": ["req.shared.accessibility"], "requirements": requirements,
            })
        cursor = {
            "stream_id": "project-ledger", "project_id": "project:alpha", "sequence": 18,
            "event_id": "event-18", "event_digest": "sha256:" + "c" * 64,
        }
        return {
            "contract_id": "screen.groups.requirements.v1", "version": "1.0.0",
            "shared_requirements": [shared], "groups": groups,
        }, {
            "accepted_scope_id": "scope:project:alpha:18", "accepted_cursor": cursor,
            "status": "KNOWN", "reason": "Bound to the accepted project ledger cursor.",
        }

    def _write_local_project_view_bundle(self, project_id: str, root: Path) -> dict[str, Any]:
        slug = project_id.removeprefix("project:")
        root.joinpath("ui").mkdir(parents=True)
        coverage = json.dumps({"schema_version": 1, "project_id": project_id, "nodes": []}, separators=(",", ":")).encode()
        graph = b'flowchart LR\n  overview["Overview"] --> review["Review"]\n'
        coverage_ref = f"project://{slug}/ui/coverage.json"
        graph_ref = f"project://{slug}/ui/app-flow.mmd"
        manifest_ref = f"project://{slug}/ui/swarm.project_views.json"
        digest = lambda value: "sha256:" + hashlib.sha256(value).hexdigest()
        requirements, binding = self._project_view_requirements_fixture()
        binding = copy.deepcopy(binding)
        binding["accepted_scope_id"] = f"scope:{project_id}:18"
        binding["accepted_cursor"]["project_id"] = project_id
        manifest = json.dumps({
            "manifest_type": "swarm.project_views", "schema_version": 1,
            "manifest_id": f"{slug}-project-views", "manifest_version": 18, "project_id": project_id,
            "projection_binding": binding, "screen_group_requirements": requirements,
            "project_tab": {
                "id": "tab.project.ui", "label": "UI", "visibility": "conditional",
                "modes": ["view.project.ui.screens", "view.project.ui.map"],
            },
            "views": [
                {
                    "id": "view.project.ui.screens", "label": "Screens", "renderer": "gallery", "mode": "grid",
                    "source_refs": [coverage_ref], "source_digests": [digest(coverage)],
                    "allowed_actions": ["open_artifact"],
                },
                {
                    "id": "view.project.ui.map", "label": "Map", "renderer": "canvas", "mode": "network",
                    "source_refs": [graph_ref], "source_digests": [digest(graph)],
                    "allowed_actions": ["open_entity"],
                },
            ],
        }, separators=(",", ":")).encode()
        manifest_digest = digest(manifest)
        root.joinpath("ui", "coverage.json").write_bytes(coverage)
        root.joinpath("ui", "app-flow.mmd").write_bytes(graph)
        root.joinpath("ui", "swarm.project_views.json").write_bytes(manifest)
        link = {
            "schema_version": 1,
            "links": [{"rel": "project_views", "ref": manifest_ref, "digest": manifest_digest}],
        }
        root.joinpath("SWARM.md").write_text("# Project\n\n```json\n" + json.dumps(link) + "\n```\n", encoding="utf-8")
        return {"manifest": manifest, "manifest_digest": manifest_digest, "link": link, "binding": binding}

    def _write_v6_project_view_bundle(self, project_id: str, root: Path) -> dict[str, Any]:
        def encoded(value: dict[str, Any]) -> bytes:
            return json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8")

        def digest(value: bytes) -> str:
            return "sha256:" + hashlib.sha256(value).hexdigest()

        slug = project_id.removeprefix("project:")
        root.mkdir(parents=True)
        coverage_ref = f"project://{slug}/dogfood/screens.json"
        map_ref = f"project://{slug}/dogfood/app-flow.json"
        mermaid_ref = f"project://{slug}/dogfood/app-flow.mmd"
        document_ref = f"project://{slug}/dogfood/master-plan.json"
        text_ref = f"project://{slug}/dogfood/master-plan.md"
        roadmap_ref = f"project://{slug}/dogfood/roadmap.json"
        flow_ref = f"project://{slug}/dogfood/delivery-flow.json"
        coverage = encoded({
            "schema_version": 1, "project_id": project_id,
            "nodes": [{
                "node_kind": "screen_state", "screen_id": "overview", "state_id": "default",
                "label": "Overview", "coverage_state": "DESIGNED",
                "design_alternatives": [], "implementation_evidence": [],
            }],
        })
        map_graph = encoded({
            "schema_version": 1, "flowchart_id": "graph.ui", "version": 1, "title": "UI flow",
            "nodes": [
                {"id": "group", "label": "Workspace", "type": "group", "order": 0},
                {"id": "overview", "label": "Overview", "screen_ref": "overview/default", "type": "screen", "order": 1},
            ],
            "edges": [{"id": "open-overview", "source": "group", "target": "overview", "label": "open"}],
        })
        mermaid = b'flowchart LR\n  legacy["Legacy"] --> graph["Graph"]\n'
        document = encoded({
            "schema_version": 1, "document_id": "document.master", "version": 1,
            "title": "Master plan", "snapshot_at": "2026-08-30", "canonical_text_ref": text_ref,
            "blocks": [
                {"type": "heading", "level": 2, "text": "North star"},
                {"type": "paragraph", "text": "Build the project tool."},
            ],
        })
        canonical_text = b"# Master plan\n\nBuild the project tool.\n"
        roadmap = encoded({
            "schema_version": 1, "timeline_id": "timeline.v1", "version": 1,
            "snapshot_at": "2026-08-30", "title": "Roadmap",
            "events": [
                {"id": "later", "label": "Later", "sequence": 20, "status": "queued", "summary": "Later work", "exit_criteria": "Review"},
                {"id": "now", "label": "Now", "sequence": 10, "status": "active", "summary": "Current work", "exit_criteria": "Proof"},
            ],
        })
        delivery_flow = encoded({
            "schema_version": 1, "flowchart_id": "graph.delivery", "version": 1,
            "title": "Delivery flow",
            "nodes": [
                {"id": "goal", "label": "Goal", "type": "input", "order": 10},
                {"id": "ctrl", "label": "CTRL", "type": "controller", "order": 20},
            ],
            "edges": [{"id": "goal-ctrl", "source": "goal", "target": "ctrl", "label": "route"}],
        })
        payloads = {
            coverage_ref: coverage, map_ref: map_graph, mermaid_ref: mermaid,
            document_ref: document, text_ref: canonical_text, roadmap_ref: roadmap, flow_ref: delivery_flow,
        }
        sources = {
            "coverage.screens": {"kind": "coverage.screens", "ref": coverage_ref, "digest": digest(coverage)},
            "graph.canonical": {"kind": "graph.json", "ref": map_ref, "digest": digest(map_graph)},
            "graph.mermaid": {"kind": "graph.mermaid", "ref": mermaid_ref, "digest": digest(mermaid)},
            "plan.master": {
                "kind": "document.blocks", "ref": document_ref, "digest": digest(document),
                "canonical_text_ref": text_ref, "canonical_text_digest": digest(canonical_text),
            },
            "plan.roadmap": {"kind": "events.timeline", "ref": roadmap_ref, "digest": digest(roadmap)},
            "plan.delivery_flow": {"kind": "graph.json", "ref": flow_ref, "digest": digest(delivery_flow)},
        }
        manifest = {
            "manifest_type": "swarm.project_views", "schema_version": 1,
            "manifest_id": "project-views-v6", "manifest_version": 6, "project_id": project_id,
            "projection_binding": {
                "accepted_scope_id": None, "accepted_cursor": None, "status": "UNKNOWN",
                "source_manifest_id": "source.v1", "source_manifest_version": 1,
                "source_manifest_digest": "sha256:" + "a" * 64,
                "reason": "Static project snapshot has no accepted live cursor.",
                "unknown_policy": "Fail closed.",
            },
            "sources": sources,
            "renderer_registry": {"registered": ["canvas", "table", "timeline", "gallery", "compare", "document"]},
            "project_tab": {
                "id": "tab.project.ui", "label": "Workspace", "visibility": "conditional",
                "modes": [
                    "view.project.plan.master", "view.project.plan.roadmap", "view.project.plan.flow",
                    "view.project.ui.screens", "view.project.ui.map",
                ],
            },
            "views": [
                {"id": "view.project.ui.screens", "label": "Screens", "renderer": "gallery", "mode": "grid", "sources": [sources["coverage.screens"]], "allowed_actions": ["open_artifact", "open_entity"]},
                {"id": "view.project.ui.map", "label": "Map", "renderer": "canvas", "mode": "network", "sources": [sources["graph.canonical"]], "allowed_actions": ["open_artifact", "open_entity"]},
                {"id": "view.project.plan.master", "label": "Master plan", "renderer": "document", "mode": "blocks", "sources": [{"kind": "document.blocks", "ref": document_ref, "digest": digest(document)}], "allowed_actions": ["open_entity", "request_review", "send_feedback"]},
                {"id": "view.project.plan.roadmap", "label": "Roadmap", "renderer": "timeline", "mode": "milestones", "sources": [sources["plan.roadmap"]], "allowed_actions": ["open_entity", "request_review", "send_feedback"]},
                {"id": "view.project.plan.flow", "label": "Flowchart", "renderer": "canvas", "mode": "network", "sources": [sources["plan.delivery_flow"]], "allowed_actions": ["open_entity", "request_review", "send_feedback"]},
            ],
            "authority": {"project_metadata_only": True, "second_status_authority": False},
        }
        manifest_bytes = encoded(manifest)
        manifest_ref = f"project://{slug}/dogfood/project-views.json"
        manifest_digest = digest(manifest_bytes)
        root.joinpath("SWARM.md").write_text(
            "# Project\n\n```json\n" + json.dumps({
                "schema_version": 1, "links": [{"rel": "project_views", "ref": manifest_ref, "digest": manifest_digest}],
            }) + "\n```\n",
            encoding="utf-8",
        )
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE project_roots SET path=? WHERE project_id=?", (str(root), project_id))
            connection.commit()
        return {
            "manifest": manifest, "manifest_bytes": manifest_bytes, "manifest_ref": manifest_ref,
            "manifest_digest": manifest_digest,
            "sources": {
                (ref, digest(value)): value for ref, value in payloads.items()
            } | {(manifest_ref, manifest_digest): manifest_bytes},
        }

    def test_project_view_custom_composes_native_work_without_changing_custom_identity(self) -> None:
        root = self.root / "composed-work"
        bundle = self._write_v6_project_view_bundle("project:alpha", root)
        app = console.App(
            self.codex_home, self.config, self.root / "console" / "composed.sqlite3",
            project_view_resolver=lambda project_id, ref, digest: bundle["sources"][(ref, digest)],
        )
        custom = app._project_view_projection("project:alpha")
        link = {"rel": "project_views", "ref": bundle["manifest_ref"], "digest": bundle["manifest_digest"]}
        self._write_project_brief(root, "project:alpha", links=[link], extra={"tasks": []})
        original = (root / "SWARM.md").read_bytes()
        briefs = app._project_briefs_projection()
        composed = app._project_view_projection("project:alpha", briefs)
        self.assertEqual(composed["views"][:-1], custom["views"])
        self.assertEqual(composed["modes"][:-1], custom["modes"])
        self.assertEqual(composed["identity"], custom["identity"])
        self.assertEqual(composed["views"][-1]["id"], "view.project.work")
        native = composed["components"][1]
        self.assertEqual(native["status"], "CURRENT")
        self.assertEqual(composed["effective_component_status"], {"custom": "CURRENT", "native_work": "CURRENT"})
        self.assertEqual(composed["views"][-1]["allowed_actions"], [])
        self.assertEqual(native["allowed_actions"], [])
        self.assertEqual(native["projection_binding"]["project_briefs_cursor"], briefs["cursor"])
        self.assertEqual(native["view_digest"], composed["views"][-1]["view_digest"])
        self.assertEqual((root / "SWARM.md").read_bytes(), original)
        self.assertEqual(app._project_view_projection("project:alpha", briefs), composed)

        stale = copy.deepcopy(briefs)
        next(row for row in stale["projects"] if row["project_id"] == "project:alpha")["digest"] = "sha256:" + "0" * 64
        withheld = app._project_view_projection("project:alpha", stale)
        self.assertEqual(withheld["views"], custom["views"])
        self.assertEqual(withheld["components"][1]["status"], "WITHHELD")
        self.assertEqual(withheld["identity"], custom["identity"])

        duplicate = copy.deepcopy(custom)
        duplicate["views"].append(copy.deepcopy(composed["views"][-1]))
        with mock.patch.object(app, "_normalize_project_view", return_value=duplicate):
            result = app._project_view_projection("project:alpha", briefs)
        self.assertEqual(result["views"], duplicate["views"])
        self.assertEqual(result["components"][1]["reason"], "DUPLICATE_WORK")

        suffix = copy.deepcopy(custom)
        suffix["views"][0]["id"] = "view.custom.work"
        suffix["modes"][0].update(id="work", view_id="view.custom.work")
        with mock.patch.object(app, "_normalize_project_view", return_value=copy.deepcopy(suffix)):
            collision = app._project_view_projection("project:alpha", briefs)
        self.assertEqual(collision["views"], suffix["views"])
        self.assertEqual(collision["modes"], suffix["modes"])
        self.assertEqual(sum(mode["id"] == "work" for mode in collision["modes"]), 1)
        self.assertEqual(collision["components"][1]["reason"], "DUPLICATE_WORK")
        self.assertEqual(collision["effective_component_status"], {"custom": "CURRENT", "native_work": "WITHHELD"})

        self._write_project_brief(root, "project:alpha", links=[link], extra={
            "tasks": [], "objective": {"current": "Changed accepted brief"},
        })
        changed = app._project_view_projection("project:alpha")
        self.assertEqual(changed["views"][:-1], custom["views"])
        self.assertNotEqual(changed["components"][1]["source_digest"], native["source_digest"])
        self.assertNotEqual(changed["composition_digest"], composed["composition_digest"])
        with mock.patch.object(app, "_resolve_project_view_bytes", side_effect=console.ConsoleError("unavailable")):
            retained = app._project_view_projection("project:alpha")
        self.assertEqual(retained.pop("status"), "STALE_LAST_ACCEPTED")
        self.assertEqual(retained.pop("effective_component_status"), {"custom": "STALE_LAST_ACCEPTED", "native_work": "STALE_LAST_ACCEPTED"})
        self.assertEqual(retained["views"][-1]["allowed_actions"], [])
        self.assertEqual(retained, {key: value for key, value in changed.items() if key != "effective_component_status"})

        self._write_project_brief(root, "project:alpha", links=[link], extra={"tasks": "invalid"})
        invalid = app._project_view_projection("project:alpha")
        self.assertEqual(invalid["views"], custom["views"])
        self.assertEqual(invalid["components"][1]["status"], "WITHHELD")

    def test_project_view_v6_workspace_projection_is_ordered_typed_and_snapshot_only(self) -> None:
        root = self.root / "projects" / "v6"
        bundle = self._write_v6_project_view_bundle("project:alpha", root)
        calls: list[tuple[str, str]] = []

        def resolve(project_id: str, ref: str, expected_digest: str) -> bytes:
            calls.append((project_id, ref))
            return bundle["sources"][(ref, expected_digest)]

        app = console.App(
            self.codex_home, self.config, self.root / "console" / "project-view-v6.sqlite3",
            project_view_resolver=resolve,
        )
        with mock.patch.object(app.store, "proof_feed", return_value=[]):
            projection = app._project_view_projection("project:alpha")
            normalized = app.project_ui_agent_read({
                "contract_id": "project.ui.agent_read.v1", "version": "1.0.0",
                "operation": "project_views.get_normalized_manifest", "project_id": "project:alpha",
            })
            catalog = app.project_ui_agent_read({
                "contract_id": "project.ui.agent_read.v1", "version": "1.0.0",
                "operation": "project_views.list_projects_with_manifests",
            })
        self.assertIsNotNone(projection)
        self.assertEqual(projection["tab"], {
            "id": "ui", "label": "Workspace", "manifest_id": "tab.project.ui", "visibility": "conditional",
        })
        self.assertEqual(
            [mode["id"] for mode in projection["modes"]],
            ["master", "roadmap", "flow", "screens", "map"],
        )
        self.assertEqual(
            [view["id"] for view in projection["views"]],
            [
                "view.project.plan.master", "view.project.plan.roadmap", "view.project.plan.flow",
                "view.project.ui.screens", "view.project.ui.map",
            ],
        )
        views = {view["id"]: view for view in projection["views"]}
        self.assertEqual(views["view.project.plan.master"]["content"]["document"]["blocks"][0]["type"], "heading")
        self.assertEqual(views["view.project.plan.master"]["content"]["canonical_text"]["digest"], bundle["manifest"]["sources"]["plan.master"]["canonical_text_digest"])
        self.assertEqual([event["id"] for event in views["view.project.plan.roadmap"]["content"]["timeline"]["events"]], ["now", "later"])
        self.assertEqual([node["id"] for node in views["view.project.plan.flow"]["content"]["graph"]["nodes"]], ["goal", "ctrl"])
        self.assertTrue(views["view.project.plan.master"]["snapshot_only"])
        self.assertTrue(views["view.project.plan.roadmap"]["snapshot_only"])
        self.assertFalse(views["view.project.plan.flow"]["snapshot_only"])
        self.assertEqual(views["view.project.ui.map"]["content"]["graph"]["nodes"][1]["screen_key"], "overview/default")
        self.assertEqual(projection["authority"]["snapshot_views"], ["view.project.plan.master", "view.project.plan.roadmap"])
        self.assertEqual(normalized["data"]["views"], projection["views"])
        self.assertEqual([item["project_id"] for item in catalog["data"]], ["project:alpha"])
        self.assertEqual(catalog["data"][0]["conditional_tabs"][0], projection["tab"])
        self.assertEqual(len(projection["source_bindings"]), 7)
        self.assertEqual(len(projection["identity"]["source_digests"]), 7)
        self.assertTrue(all(project_id == "project:alpha" for project_id, _ in calls))
        called_refs = {ref for _, ref in calls}
        expected_refs = {ref for ref, _ in bundle["sources"] if ref != bundle["manifest_ref"]}
        self.assertTrue(expected_refs.issubset(called_refs))

    def test_project_view_v6_invalid_manifest_preserves_last_accepted_projection(self) -> None:
        root = self.root / "projects" / "v6-invalid"
        bundle = self._write_v6_project_view_bundle("project:alpha", root)
        sources = dict(bundle["sources"])
        app = console.App(
            self.codex_home, self.config, self.root / "console" / "project-view-v6-invalid.sqlite3",
            project_view_resolver=lambda _project_id, ref, expected: sources[(ref, expected)],
        )
        with mock.patch.object(app.store, "proof_feed", return_value=[]):
            accepted = app._project_view_projection("project:alpha")
        self.assertIsNotNone(accepted)

        unknown_renderer = copy.deepcopy(bundle["manifest"])
        unknown_renderer["views"][0]["renderer"] = "unknown"
        unknown_renderer_bytes = json.dumps(unknown_renderer, separators=(",", ":")).encode()
        with self.assertRaisesRegex(console.ConsoleError, "renderer is not registered"):
            app._normalize_project_view("project:alpha", unknown_renderer_bytes, "sha256:" + hashlib.sha256(unknown_renderer_bytes).hexdigest())

        unknown_mode = copy.deepcopy(bundle["manifest"])
        unknown_mode["views"][0]["mode"] = "unknown"
        unknown_mode_bytes = json.dumps(unknown_mode, separators=(",", ":")).encode()
        with self.assertRaisesRegex(console.ConsoleError, "mode is not registered"):
            app._normalize_project_view("project:alpha", unknown_mode_bytes, "sha256:" + hashlib.sha256(unknown_mode_bytes).hexdigest())

        duplicate_source = copy.deepcopy(bundle["manifest"])
        duplicate_source["sources"]["duplicate"] = copy.deepcopy(duplicate_source["sources"]["graph.canonical"])
        duplicate_bytes = json.dumps(duplicate_source, separators=(",", ":")).encode()
        with self.assertRaisesRegex(console.ConsoleError, "source reference is duplicated"):
            app._normalize_project_view("project:alpha", duplicate_bytes, "sha256:" + hashlib.sha256(duplicate_bytes).hexdigest())

        bad_text = copy.deepcopy(bundle["manifest"])
        bad_text["sources"]["plan.master"]["canonical_text_digest"] = "sha256:" + "f" * 64
        bad_text_bytes = json.dumps(bad_text, separators=(",", ":")).encode()
        sources[(bad_text["sources"]["plan.master"]["canonical_text_ref"], bad_text["sources"]["plan.master"]["canonical_text_digest"])] = sources[(bundle["manifest"]["sources"]["plan.master"]["canonical_text_ref"], bundle["manifest"]["sources"]["plan.master"]["canonical_text_digest"])]
        with self.assertRaisesRegex(console.ConsoleError, "source digest does not match"):
            app._normalize_project_view("project:alpha", bad_text_bytes, "sha256:" + hashlib.sha256(bad_text_bytes).hexdigest())

        invalid_digest = "sha256:" + "0" * 64
        sources[(bundle["manifest_ref"], invalid_digest)] = unknown_renderer_bytes
        root.joinpath("SWARM.md").write_text(
            "```json\n" + json.dumps({"schema_version": 1, "links": [{"rel": "project_views", "ref": bundle["manifest_ref"], "digest": invalid_digest}]}) + "\n```\n",
            encoding="utf-8",
        )
        with mock.patch.object(app.store, "proof_feed", return_value=[]):
            retained = app._project_view_projection("project:alpha")
        self.assertEqual(retained.pop("status"), "STALE_LAST_ACCEPTED")
        self.assertEqual(retained.pop("effective_component_status"), {"custom": "STALE_LAST_ACCEPTED", "native_work": "WITHHELD"})
        self.assertEqual(retained, {key: value for key, value in accepted.items() if key != "effective_component_status"})

    def test_default_project_view_resolver_is_root_bound_and_withholds_incompatible_pilots(self) -> None:
        alpha_root = self.root / "projects" / "alpha-local"
        beta_root = self.root / "projects" / "beta-local"
        alpha = self._write_local_project_view_bundle("project:alpha", alpha_root)
        beta = self._write_local_project_view_bundle("project:beta", beta_root)
        self._add_host_project("project:beta", "beta", str(beta_root))
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE project_roots SET path=? WHERE project_id='project:alpha'", (str(alpha_root),))
            connection.execute("UPDATE threads SET cwd=? WHERE cwd='C:/work/alpha'", (str(alpha_root),))
            connection.commit()
        app = console.App(self.codex_home, self.config, self.root / "console" / "default-project-view.sqlite3")
        with mock.patch.object(app.store, "proof_feed", return_value=[]):
            alpha_projection = app._project_view_projection("project:alpha")
            beta_projection = app._project_view_projection("project:beta")
        self.assertEqual(alpha_projection["identity"]["manifest_digest"], alpha["manifest_digest"])
        self.assertEqual(beta_projection["identity"]["manifest_digest"], beta["manifest_digest"])
        self.assertEqual(alpha_projection["requirements"]["requirement_count"], 31)
        self.assertEqual(len(alpha_projection["requirements"]["groups"]), 6)
        self.assertEqual(app._root_project_view_link(alpha_root), (
            "present", {key: alpha["link"]["links"][0][key] for key in ("ref", "digest")},
        ))
        coverage_path = alpha_root / "ui" / "coverage.json"
        coverage_bytes = coverage_path.read_bytes()
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("pathname reopen")):
            self.assertEqual(app._default_project_view_resolver(
                "project:alpha", "project://alpha/ui/coverage.json",
                "sha256:" + hashlib.sha256(coverage_bytes).hexdigest(),
            ), coverage_bytes)

        with self.assertRaisesRegex(console.ConsoleError, "another project"):
            app._default_project_view_resolver("project:alpha", "project://beta/ui/coverage.json", "sha256:" + "0" * 64)
        with self.assertRaisesRegex(console.ConsoleError, "traversal"):
            app._default_project_view_resolver("project:alpha", "project://alpha/../coverage.json", "sha256:" + "0" * 64)
        with self.assertRaisesRegex(console.ConsoleError, "digest does not match"):
            app._default_project_view_resolver("project:alpha", "project://alpha/ui/coverage.json", "sha256:" + "0" * 64)
        oversized = alpha_root / "ui" / "oversized.json"
        oversized.write_bytes(b"x" * (console.PROJECT_VIEW_MAX_BYTES + 1))
        with self.assertRaisesRegex(console.ConsoleError, "exceeds the delivery guard"):
            app._default_project_view_resolver(
                "project:alpha", "project://alpha/ui/oversized.json", "sha256:" + hashlib.sha256(oversized.read_bytes()).hexdigest(),
            )
        with mock.patch.object(Path, "is_symlink", return_value=True), self.assertRaisesRegex(
            console.ConsoleError, "reparse point",
        ):
            app._default_project_view_resolver("project:alpha", "project://alpha/ui/coverage.json", "sha256:" + hashlib.sha256((alpha_root / "ui" / "coverage.json").read_bytes()).hexdigest())

        invalid_link_root = self.root / "projects" / "invalid-link"
        invalid_link_root.mkdir(parents=True)
        invalid_link_root.joinpath("SWARM.md").write_text(
            "```json\n" + json.dumps({"links": alpha["link"]["links"]}) + "\n```\n", encoding="utf-8",
        )
        self.assertEqual(app._root_project_view_link(invalid_link_root), ("invalid", None))
        invalid_link_root.joinpath("SWARM.md").write_text(
            "```json\n" + json.dumps({
                "schema_version": 1, "links": [{**alpha["link"]["links"][0], "title": "Project UI"}],
            }) + "\n```\n", encoding="utf-8",
        )
        self.assertEqual(app._root_project_view_link(invalid_link_root), ("invalid", None))

        legacy_root = self.root / "projects" / "legacy-local"
        legacy_root.joinpath("ui").mkdir(parents=True)
        legacy = json.dumps({"version": "0.1", "projectId": "project:legacy", "views": []}, separators=(",", ":")).encode()
        legacy_digest = "sha256:" + hashlib.sha256(legacy).hexdigest()
        legacy_root.joinpath("ui", "swarm.project_views.json").write_bytes(legacy)
        legacy_root.joinpath("SWARM.md").write_text(
            "```json\n" + json.dumps({"schema_version": 1, "links": [{
                "rel": "project_views", "ref": "project://legacy/ui/swarm.project_views.json", "digest": legacy_digest,
            }]}) + "\n```\n", encoding="utf-8",
        )
        self._add_host_project("project:legacy", "Legacy", str(legacy_root))
        with mock.patch.object(app.store, "proof_feed", return_value=[]):
            self.assertIsNone(app._project_view_projection("project:legacy"))

    def test_project_view_accepts_only_root_bound_runtime_id_or_unique_saved_name(self) -> None:
        runtime_id = "01a00000-0000-7000-8000-000000000001"
        root = self.root / "projects" / "swarm-runtime"
        root.mkdir(parents=True)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("INSERT INTO projects VALUES (?,?,?,?,?,?)", (runtime_id, "swarm", "{}", 7, 0, 0))
            connection.execute("INSERT INTO project_roots VALUES (?,?,?)", (runtime_id, 0, str(root)))
            connection.commit()
        app = console.App(self.codex_home, self.config, self.root / "console" / "identity-alias.sqlite3")
        self.assertEqual(app._canonical_project_identities(runtime_id), frozenset({runtime_id, "swarm"}))

        screens = json.dumps({"schema_version": 1, "project_id": "swarm", "nodes": []}).encode()
        self.assertEqual(app._project_view_screens(runtime_id, screens), [])
        runtime_screens = json.dumps({"schema_version": 1, "project_id": runtime_id, "nodes": []}).encode()
        self.assertEqual(app._project_view_screens(runtime_id, runtime_screens), [])
        with self.assertRaisesRegex(console.ConsoleError, "another project"):
            app._project_view_screens(runtime_id, json.dumps({"project_id": "other", "nodes": []}).encode())

        source = root / "coverage.json"
        source.write_bytes(screens)
        digest = "sha256:" + hashlib.sha256(screens).hexdigest()
        self.assertEqual(app._default_project_view_resolver(runtime_id, "project://swarm/coverage.json", digest), screens)
        with self.assertRaisesRegex(console.ConsoleError, "another project"):
            app._default_project_view_resolver(runtime_id, "project://other/coverage.json", digest)

        graph = b'flowchart LR\n  overview["Overview"]\n'
        graph_digest = "sha256:" + hashlib.sha256(graph).hexdigest()
        manifest = json.dumps({
            "manifest_type": "swarm.project_views", "schema_version": 1,
            "manifest_id": "swarm-views", "manifest_version": 1, "project_id": "swarm",
            "project_tab": {"id": "tab.project.ui", "label": "UI", "visibility": "conditional", "modes": ["view.project.ui.screens", "view.project.ui.map"]},
            "views": [
                {"id": "view.project.ui.screens", "label": "Screens", "renderer": "gallery", "mode": "grid", "source_refs": ["project://swarm/coverage.json"], "source_digests": [digest], "allowed_actions": ["open_artifact"]},
                {"id": "view.project.ui.map", "label": "Map", "renderer": "canvas", "mode": "network", "source_refs": ["project://swarm/graph.mmd"], "source_digests": [graph_digest], "allowed_actions": ["open_entity"]},
            ],
        }, separators=(",", ":")).encode()
        app.project_view_resolver = lambda _project_id, ref, _digest: screens if ref.endswith("coverage.json") else graph
        with mock.patch.object(app.store, "proof_feed", return_value=[]):
            normalized = app._normalize_project_view(runtime_id, manifest, "sha256:" + hashlib.sha256(manifest).hexdigest())
        self.assertEqual(normalized["project_id"], runtime_id)

        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("INSERT INTO projects VALUES (?,?,?,?,?,?)", ("duplicate", "swarm", "{}", 8, 0, 0))
            connection.commit()
        with self.assertRaisesRegex(console.ConsoleError, "ambiguous"):
            app._canonical_project_identities(runtime_id)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DELETE FROM projects WHERE id IN (?, ?)", (runtime_id, "duplicate"))
            connection.commit()
        with self.assertRaisesRegex(console.ConsoleError, "canonical saved project identity"):
            app._canonical_project_identities(runtime_id)

    def test_project_ui_agent_read_is_digest_cursor_bound_and_fail_closed(self) -> None:
        root = self.root / "projects" / "alpha-agent"
        bundle = self._write_local_project_view_bundle("project:alpha", root)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE project_roots SET path=? WHERE project_id='project:alpha'", (str(root),))
            connection.execute("UPDATE threads SET cwd=? WHERE cwd='C:/work/alpha'", (str(root),))
            connection.commit()
        app = console.App(self.codex_home, self.config, self.root / "console" / "project-agent-read.sqlite3")
        base = {
            "contract_id": "project.ui.agent_read.v1", "version": "1.0.0", "project_id": "project:alpha",
            "accepted_scope_id": bundle["binding"]["accepted_scope_id"],
            "accepted_cursor": bundle["binding"]["accepted_cursor"],
        }
        with mock.patch.object(app.store, "proof_feed", return_value=[]):
            manifest = app.project_ui_agent_read({**base, "operation": "project_views.get_normalized_manifest"})
            groups = app.project_ui_agent_read({**base, "operation": "project_views.list_screen_groups"})
            group = app.project_ui_agent_read({**base, "operation": "project_views.get_screen_group", "group_id": "group.overview"})
            first = app.project_ui_agent_read({**base, "operation": "project_views.list_requirements", "page_size": 2})
            second = app.project_ui_agent_read({**base, "operation": "project_views.list_requirements", "page_size": 2, "page_token": first["next_page_token"]})
            missing = app.project_ui_agent_read({**base, "operation": "project_views.list_missing_requirements", "target_device": "mobile"})
            graph = app.project_ui_agent_read({**base, "operation": "project_views.get_graph_identity"})
            evidence = app.project_ui_agent_read({**base, "operation": "project_views.get_evidence_identities", "requirement_id": "req.overview.1"})
            artifacts = app.project_ui_agent_read({**base, "operation": "project_views.get_artifact_identities", "requirement_id": "req.overview.1"})
            projects = app.project_ui_agent_read({
                "contract_id": "project.ui.agent_read.v1", "version": "1.0.0",
                "operation": "project_views.list_projects_with_manifests", "project_id": "project:alpha",
            })
        self.assertEqual(manifest["data"]["requirements"]["requirement_count"], 31)
        self.assertEqual((len(groups["data"]), group["data"]["group_id"]), (6, "group.overview"))
        self.assertEqual(len(first["data"]), 2)
        self.assertNotEqual(first["data"][0]["requirement_id"], second["data"][0]["requirement_id"])
        self.assertTrue(all(item["derived_state"] != "KNOWN_SATISFIED" for item in missing["data"]))
        self.assertEqual(graph["data"]["kind"], "graph")
        self.assertEqual(evidence["data"][0]["artifact_id"], "overview-preview")
        self.assertEqual(artifacts["data"][0]["artifact_id"], "overview-approved")
        self.assertEqual([item["project_id"] for item in projects["data"]], ["project:alpha"])

        hostile = [
            {**base, "operation": "project_views.list_requirements", "unknown": True},
            {**base, "operation": "project_views.get_normalized_manifest", "accepted_cursor": {**bundle["binding"]["accepted_cursor"], "sequence": 19}},
            {**base, "operation": "project_views.list_requirements", "page_token": first["next_page_token"][:-1] + "x"},
            {**base, "operation": "project_views.get_graph_identity", "group_id": "group.overview"},
            {**base, "operation": "project_views.unknown"},
        ]
        with mock.patch.object(app.store, "proof_feed", return_value=[]):
            for request in hostile:
                with self.subTest(request=request), self.assertRaises(console.ConsoleError):
                    app.project_ui_agent_read(request)

    def test_project_view_manifest_is_digest_bound_conditional_and_project_generic(self) -> None:
        def encoded(value: dict[str, Any]) -> bytes:
            return json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8")

        def digest(value: bytes) -> str:
            return "sha256:" + hashlib.sha256(value).hexdigest()

        def bundle(project_id: str, root: Path, prefix: str) -> tuple[dict[tuple[str, str], bytes], dict[str, Any]]:
            coverage_ref = f"project://{prefix}/ui/coverage"
            graph_ref = f"project://{prefix}/ui/app-flow"
            manifest_ref = f"project://{prefix}/ui/project-views"
            evidence_digest = hashlib.sha256(f"{prefix}-image".encode("utf-8")).hexdigest()
            coverage = encoded({
                "schema_version": 1,
                "project_id": project_id,
                "nodes": [
                    {
                        "node_kind": "screen_state", "screen_id": "overview", "state_id": "default",
                        "label": f"{prefix.title()} overview", "coverage_state": "DESIGNED",
                        "design_alternatives": [
                            {
                                "alternative_id": "overview-default", "label": "Default",
                                "artifact_id": f"{prefix}-overview", "evidence_id": f"{prefix}-overview",
                                "digest": f"sha256:{evidence_digest}", "device": "desktop",
                            },
                        ],
                        "implementation_evidence": [],
                    },
                    {
                        "node_kind": "screen_state", "screen_id": "assets", "state_id": "empty",
                        "label": "Assets empty", "coverage_state": "MISSING_DESIGN",
                        "design_alternatives": [], "implementation_evidence": [],
                    },
                ],
            })
            graph = (
                'flowchart LR\n'
                '  overview["Overview"] --> assets["Assets<br/>empty"]\n'
            ).encode("utf-8")
            manifest = encoded({
                "manifest_type": "swarm.project_views", "schema_version": 1,
                "manifest_id": f"{prefix}-project-views", "manifest_version": 1,
                "project_id": project_id,
                "project_tab": {
                    "id": "tab.project.ui", "label": "UI", "visibility": "conditional",
                    "modes": ["view.project.ui.screens", "view.project.ui.map"],
                },
                "views": [
                    {
                        "id": "view.project.ui.screens", "label": "Screens", "renderer": "gallery", "mode": "grid",
                        "source_refs": [coverage_ref], "source_digests": [digest(coverage)],
                        "allowed_actions": ["open_artifact", "send_feedback"],
                    },
                    {
                        "id": "view.project.ui.map", "label": "Map", "renderer": "canvas", "mode": "network",
                        "source_refs": [graph_ref], "source_digests": [digest(graph)],
                        "allowed_actions": ["open_entity", "send_feedback"],
                    },
                ],
            })
            manifest_digest = digest(manifest)
            root.mkdir(parents=True)
            root.joinpath("SWARM.md").write_text(
                "# Project\n\n```json\n" + json.dumps({
                    "schema_version": 1,
                    "links": [{"rel": "project_views", "ref": manifest_ref, "digest": manifest_digest}],
                }) + "\n```\n",
                encoding="utf-8",
            )
            return {
                (manifest_ref, manifest_digest): manifest,
                (coverage_ref, digest(coverage)): coverage,
                (graph_ref, digest(graph)): graph,
            }, {
                "evidence_id": f"{prefix}-overview", "task_id": "task", "project_id": project_id,
                "kind": "screenshot", "caption": f"{prefix.title()} overview", "claim_limit": "source preview",
                "disposition": "PENDING", "surface_kind": "browser", "media_type": "image/png",
                "size_bytes": 1, "digest": evidence_digest, "registered_at_ms": 1, "updated_at_ms": 1,
            }

        alpha_root = self.root / "projects" / "alpha"
        alpha_sources, alpha_proof = bundle("project:alpha", alpha_root, "alpha")
        beta_root = self.root / "projects" / "beta"
        beta_sources, beta_proof = bundle("project:beta", beta_root, "beta")
        self._add_host_project("project:beta", "beta", str(beta_root))
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE project_roots SET path=? WHERE project_id='project:alpha'", (str(alpha_root),))
            connection.execute("UPDATE threads SET cwd=? WHERE cwd='C:/work/alpha'", (str(alpha_root),))
            connection.commit()
        sources = {**alpha_sources, **beta_sources}
        calls: list[tuple[str, str, str]] = []

        def resolve(project_id: str, ref: str, expected_digest: str) -> bytes:
            calls.append((project_id, ref, expected_digest))
            return sources[(ref, expected_digest)]

        app = console.App(
            self.codex_home, self.config, self.root / "console" / "project-views.sqlite3",
            project_view_resolver=resolve,
        )
        link_status, alpha_link = app._root_project_view_link(alpha_root)
        self.assertEqual(link_status, "present")
        self.assertIsNotNone(alpha_link)
        with mock.patch.object(app.store, "proof_feed", side_effect=lambda *, project_id=None, task_id=None: [
            item for item in (alpha_proof, beta_proof) if project_id in {None, item["project_id"]}
        ]):
            alpha_bytes = app._resolve_project_view_bytes("project:alpha", alpha_link["ref"], alpha_link["digest"])
            app._normalize_project_view("project:alpha", alpha_bytes, alpha_link["digest"])
            alpha = app.overview("project:alpha")["project_view"]
            beta = app._project_view_projection("project:beta")
        self.assertEqual(alpha["tab"], {"id": "ui", "label": "UI"})
        self.assertEqual([mode["label"] for mode in alpha["modes"]], ["Screens", "Map"])
        self.assertEqual([screen["id"] for screen in alpha["screens"]], ["overview/default", "assets/empty"])
        self.assertEqual(alpha["screens"][0]["devices"], ["desktop"])
        self.assertEqual(alpha["screens"][0]["alternative_count"], 1)
        self.assertEqual(alpha["screens"][1]["evidence"], [])
        self.assertEqual(alpha["map"]["nodes"][0]["screen_key"], "overview/default")
        self.assertEqual(beta["project_id"], "project:beta")
        self.assertEqual(beta["screens"][0]["label"], "Beta overview")
        self.assertTrue(any(call[0] == "project:alpha" for call in calls))
        self.assertTrue(any(call[0] == "project:beta" for call in calls))
        self.assertNotIn(str(alpha_root), json.dumps(alpha))
        self.assertNotIn(str(beta_root), json.dumps(beta))

    def test_project_view_manifest_failure_is_withheld_or_preserves_last_good(self) -> None:
        root = self.root / "projects" / "alpha"
        root.mkdir(parents=True)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE project_roots SET path=? WHERE project_id='project:alpha'", (str(root),))
            connection.commit()
        app = console.App(
            self.codex_home, self.config, self.root / "console" / "project-view-failure.sqlite3",
            project_view_resolver=lambda *_: b"{}",
        )
        self.assertIsNone(app._project_view_projection("project:alpha"))

        coverage = json.dumps({"project_id": "project:alpha", "nodes": []}, separators=(",", ":")).encode()
        graph = b'flowchart LR\n  start["Start"] --> finish["Finish"]\n'
        coverage_digest = "sha256:" + hashlib.sha256(coverage).hexdigest()
        graph_digest = "sha256:" + hashlib.sha256(graph).hexdigest()
        manifest_ref = "project://alpha/ui/project-views"
        coverage_ref = "project://alpha/ui/coverage"
        graph_ref = "project://alpha/ui/app-flow"
        manifest = json.dumps({
            "manifest_type": "swarm.project_views", "schema_version": 1,
            "manifest_id": "alpha-views", "manifest_version": 1, "project_id": "project:alpha",
            "project_tab": {"id": "tab.project.ui", "label": "UI", "visibility": "conditional", "modes": ["view.project.ui.screens", "view.project.ui.map"]},
            "views": [
                {"id": "view.project.ui.screens", "label": "Screens", "renderer": "gallery", "mode": "grid", "source_refs": [coverage_ref], "source_digests": [coverage_digest], "allowed_actions": ["open_artifact"]},
                {"id": "view.project.ui.map", "label": "Map", "renderer": "canvas", "mode": "network", "source_refs": [graph_ref], "source_digests": [graph_digest], "allowed_actions": ["open_entity"]},
            ],
        }, separators=(",", ":")).encode()
        manifest_digest = "sha256:" + hashlib.sha256(manifest).hexdigest()
        sources = {
            (manifest_ref, manifest_digest): manifest,
            (coverage_ref, coverage_digest): coverage,
            (graph_ref, graph_digest): graph,
        }
        app.project_view_resolver = lambda project_id, ref, expected: sources[(ref, expected)]
        root.joinpath("SWARM.md").write_text(
            "```json\n" + json.dumps({"schema_version": 1, "links": [{"rel": "project_views", "ref": manifest_ref, "digest": manifest_digest}]}) + "\n```\n",
            encoding="utf-8",
        )
        link_status, accepted_link = app._root_project_view_link(root)
        self.assertEqual(link_status, "present")
        self.assertIsNotNone(accepted_link)
        with mock.patch.object(app.store, "proof_feed", return_value=[]):
            accepted_bytes = app._resolve_project_view_bytes("project:alpha", accepted_link["ref"], accepted_link["digest"])
            app._normalize_project_view("project:alpha", accepted_bytes, accepted_link["digest"])
            accepted = app._project_view_projection("project:alpha")
        self.assertEqual(accepted["identity"]["manifest_digest"], manifest_digest)

        conflicting = json.loads(manifest)
        conflicting["views"][1]["source_refs"] = [coverage_ref]
        conflicting_bytes = json.dumps(conflicting, separators=(",", ":")).encode()
        with self.assertRaisesRegex(console.ConsoleError, "conflicting digests"):
            app._normalize_project_view("project:alpha", conflicting_bytes, "sha256:" + hashlib.sha256(conflicting_bytes).hexdigest())

        duplicated = json.loads(manifest)
        duplicated["views"][1]["source_refs"] = [coverage_ref]
        duplicated["views"][1]["source_digests"] = [coverage_digest]
        duplicated_bytes = json.dumps(duplicated, separators=(",", ":")).encode()
        with self.assertRaisesRegex(console.ConsoleError, "duplicated"):
            app._normalize_project_view("project:alpha", duplicated_bytes, "sha256:" + hashlib.sha256(duplicated_bytes).hexdigest())

        malformed_graph = b'flowchart LR\n  start["Start"] --> finish["Finish"]\n  style start fill:#fff\n'
        malformed_digest = "sha256:" + hashlib.sha256(malformed_graph).hexdigest()
        sources[(graph_ref, malformed_digest)] = malformed_graph
        malformed = json.loads(manifest)
        malformed["views"][1]["source_digests"] = [malformed_digest]
        malformed_bytes = json.dumps(malformed, separators=(",", ":")).encode()
        with self.assertRaisesRegex(console.ConsoleError, "unsupported Mermaid syntax"):
            app._normalize_project_view("project:alpha", malformed_bytes, "sha256:" + hashlib.sha256(malformed_bytes).hexdigest())

        missing_evidence_digest = hashlib.sha256(b"missing-evidence").hexdigest()
        missing_evidence = json.dumps({
            "project_id": "project:alpha",
            "nodes": [{
                "node_kind": "screen_state", "screen_id": "overview", "state_id": "default",
                "design_alternatives": [{
                    "artifact_id": "missing", "evidence_id": "missing",
                    "digest": "sha256:" + missing_evidence_digest, "device": "desktop",
                }],
                "implementation_evidence": [],
            }],
        }, separators=(",", ":")).encode()
        with mock.patch.object(app.store, "proof_feed", return_value=[]), self.assertRaisesRegex(
            console.ConsoleError, "not retained at its exact digest",
        ):
            app._project_view_screens("project:alpha", missing_evidence)

        retained_digest = hashlib.sha256(b"retained-evidence").hexdigest()
        unknown_device = json.dumps({
            "project_id": "project:alpha",
            "nodes": [{
                "node_kind": "screen_state", "screen_id": "overview", "state_id": "default",
                "design_alternatives": [{
                    "artifact_id": "retained", "evidence_id": "retained",
                    "digest": "sha256:" + retained_digest, "device": "watch",
                }],
                "implementation_evidence": [],
            }],
        }, separators=(",", ":")).encode()
        with mock.patch.object(app.store, "proof_feed", return_value=[{
            "evidence_id": "retained", "digest": retained_digest, "media_type": "image/png",
        }]), self.assertRaisesRegex(console.ConsoleError, "device is unsupported"):
            app._project_view_screens("project:alpha", unknown_device)

        unknown = json.loads(manifest)
        unknown["manifest_version"] = 2
        unknown["views"][0]["renderer"] = "arbitrary-component"
        unknown_bytes = json.dumps(unknown, separators=(",", ":")).encode()
        unknown_digest = "sha256:" + hashlib.sha256(unknown_bytes).hexdigest()
        sources[(manifest_ref, unknown_digest)] = unknown_bytes
        root.joinpath("SWARM.md").write_text(
            "```json\n" + json.dumps({"schema_version": 1, "links": [{"rel": "project_views", "ref": manifest_ref, "digest": unknown_digest}]}) + "\n```\n",
            encoding="utf-8",
        )
        with mock.patch.object(app.store, "proof_feed", return_value=[]):
            retained = app._project_view_projection("project:alpha")
        self.assertEqual(retained.pop("status"), "STALE_LAST_ACCEPTED")
        self.assertEqual(retained.pop("effective_component_status"), {"custom": "STALE_LAST_ACCEPTED", "native_work": "WITHHELD"})
        self.assertEqual(retained, {key: value for key, value in accepted.items() if key != "effective_component_status"})
        fresh = console.App(
            self.codex_home, self.config, self.root / "console" / "project-view-fresh.sqlite3",
            project_view_resolver=lambda project_id, ref, expected: sources[(ref, expected)],
        )
        with mock.patch.object(fresh.store, "proof_feed", return_value=[]):
            self.assertIsNone(fresh._project_view_projection("project:alpha"))

    def test_project_view_flowchart_json_is_typed_screen_bound_and_fail_closed(self) -> None:
        app = console.App(self.codex_home, self.config)
        screens = [
            {"id": "overview/default", "screen_id": "overview", "state_id": "default", "evidence": [{"device": "desktop"}, {"device": "tablet"}, {"device": "mobile"}]},
            {"id": "review/default", "screen_id": "review", "state_id": "default", "evidence": []},
        ]
        graph = {
            "schema_version": 1,
            "flowchart_id": "main-flow",
            "version": 3,
            "nodes": [
                {"id": "group-main", "label": "Main", "type": "group", "visibility": "visible", "order": 0},
                {"id": "overview-node", "label": "Overview", "screen_ref": "overview/default", "group_id": "group-main", "type": "screen", "visibility": "visible", "order": 1, "layout": {"x": 10, "y": 20}},
                {"id": "review-node", "label": "Review", "screen_ref": "review", "group_id": "group-main", "type": "screen", "visibility": "conditional", "order": 2},
            ],
            "edges": [
                {"id": "edge-overview-review", "source": "overview-node", "target": "review-node", "label": "Continue", "type": "navigation", "condition": "review available"},
            ],
        }
        normalized = app._project_view_graph(json.dumps(graph).encode(), screens)
        self.assertEqual((normalized["flowchart_id"], normalized["version"]), ("main-flow", 3))
        self.assertEqual(normalized["nodes"][1]["screen_key"], "overview/default")
        self.assertEqual(normalized["nodes"][2]["screen_key"], "review/default")
        self.assertEqual(normalized["edges"][0]["id"], "edge-overview-review")
        self.assertEqual(screens[0]["evidence"][0]["device"], "desktop")

        for invalid_version in (True, 1.0, "1", 0, 2):
            invalid_schema = copy.deepcopy(graph)
            invalid_schema["schema_version"] = invalid_version
            with self.subTest(schema_version=invalid_version), self.assertRaisesRegex(
                console.ConsoleError, "schema is unsupported",
            ):
                app._project_view_graph(json.dumps(invalid_schema).encode(), screens)

        cases = []
        duplicate_node = copy.deepcopy(graph)
        duplicate_node["nodes"].append(copy.deepcopy(duplicate_node["nodes"][0]))
        cases.append((duplicate_node, "node identities"))
        duplicate_edge = copy.deepcopy(graph)
        duplicate_edge["edges"].append(copy.deepcopy(duplicate_edge["edges"][0]))
        cases.append((duplicate_edge, "edge identities"))
        unknown_ref = copy.deepcopy(graph)
        unknown_ref["nodes"][1]["screen_ref"] = "missing"
        cases.append((unknown_ref, "unknown or ambiguous"))
        unknown_version = copy.deepcopy(graph)
        unknown_version["schema_version"] = 2
        cases.append((unknown_version, "schema is unsupported"))
        unknown_field = copy.deepcopy(graph)
        unknown_field["extra"] = True
        cases.append((unknown_field, "schema is unsupported"))
        executable = copy.deepcopy(graph)
        executable["nodes"][1]["component"] = "javascript:run()"
        cases.append((executable, "executable links|node is invalid"))
        missing_endpoint = copy.deepcopy(graph)
        missing_endpoint["edges"][0]["target"] = "missing"
        cases.append((missing_endpoint, "unknown node"))
        for candidate, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(console.ConsoleError, message):
                app._project_view_graph(json.dumps(candidate).encode(), screens)

        ambiguous_screens = screens + [
            {"id": "overview/empty", "screen_id": "overview", "state_id": "empty", "evidence": []},
        ]
        ambiguous = copy.deepcopy(graph)
        ambiguous["nodes"][1]["screen_ref"] = "overview"
        with self.assertRaisesRegex(console.ConsoleError, "unknown or ambiguous"):
            app._project_view_graph(json.dumps(ambiguous).encode(), ambiguous_screens)

        mermaid = app._project_view_graph(b'flowchart LR\n  overview["Overview"] --> review["Review"]\n', screens)
        self.assertNotIn("flowchart_id", mermaid)
        self.assertEqual(mermaid["nodes"][0]["screen_key"], "overview/default")

    def test_proof_visuals_are_immediate_replay_safe_and_independent_of_review_annotations(self) -> None:
        self._confirm_root_ctrl()
        app = console.App(self.codex_home, self.config, self.root / "console" / "proof-feed.sqlite3")
        self._append_notification_fixture(app)
        self._write_proof_event("feed-proof", "task")
        first = app.run_log("root", project_id="project:alpha")
        second = app.run_log("root", project_id="project:alpha")
        self.assertEqual(first["proof_items"], second["proof_items"])
        self.assertEqual([item["evidence_id"] for item in first["proof_items"]], ["feed-proof"])
        self.assertEqual(first["proof_status"], "available")
        self.assertEqual(first["proof_cursor"], second["proof_cursor"])
        self.assertIn("review-requested", {item["event_id"] for item in first["items"]})
        feed = app.project_progress_feed("project:alpha")
        replay = app.project_progress_feed("project:alpha")
        self.assertEqual(feed["proof_items"], replay["proof_items"])
        self.assertEqual([item["evidence_id"] for item in feed["proof_items"]], ["feed-proof"])

    def test_proof_store_failures_are_explicit_unavailable_or_partial(self) -> None:
        self._confirm_root_ctrl()
        app = console.App(self.codex_home, self.config, self.root / "console" / "proof-status.sqlite3")
        self._append_notification_fixture(app)
        with mock.patch.object(
            app.store, "proof_feed", side_effect=sqlite3.OperationalError("proof store unavailable")
        ):
            run_log = app.run_log("root", project_id="project:alpha")
            project_feed = app.project_progress_feed("project:alpha")
        self.assertEqual(run_log["proof_status"], "unavailable")
        self.assertEqual(run_log["proof_cursor"], {"sequence": None, "identity": None})
        self.assertEqual(project_feed["proof_status"], "unavailable")
        self.assertEqual(project_feed["proof_cursor"], {"sequence": None, "identity": None})

        with mock.patch.object(
            app, "_ingest_proof_events_if_changed",
            return_value={
                "imported": 0, "duplicates": 0, "rejected": 1,
                "retryable": 0, "capped": 0, "enumerated": 1,
            },
        ):
            partial = app.run_log("root", project_id="project:alpha")
        self.assertEqual(partial["proof_status"], "partial")
        self.assertIsInstance(partial["proof_cursor"]["identity"], str)

    def test_proof_media_delivery_requires_registered_surface_and_current_digest(self) -> None:
        media_path = self.root / "proof.png"
        media_path.write_bytes(b"\x89PNG\r\n\x1a\nproof")
        store = console.ConsoleStore(self.root / "console" / "delivery.sqlite3")
        base = {
            "source": "CtrlEvidence", "evidence_id": "evidence-delivery", "task_id": "task-1",
            "project_id": "project:alpha", "kind": "screenshot", "locator": str(media_path),
            "caption": "Screenshot proof", "claim_limit": "Local screenshot only.",
            "receipt": "proof-event:evidence-delivery", "surface_kind": "available_media", "disposition": "PENDING",
        }
        registered = store.record_proof_media(base, now_ms=2)
        item = store.proof_media_item("evidence-delivery", registered["digest"])
        self.assertEqual(item["media_type"], "image/png")
        self.assertEqual(item["size_bytes"], len(b"\x89PNG\r\n\x1a\nproof"))
        other_root = self.root / "other-proof-root"
        other_root.mkdir()
        with self.assertRaisesRegex(console.ConsoleError, "configured evidence store"):
            store.proof_media_item("evidence-delivery", registered["digest"], allowed_root=other_root)
        with self.assertRaises(console.ConsoleError):
            store.proof_media_item("evidence-delivery", "0" * 64)
        media_path.write_bytes(b"changed")
        with self.assertRaises(console.ConsoleError):
            store.proof_media_item("evidence-delivery", registered["digest"])

    def test_proof_event_ingestion_derives_project_and_enforces_media_root(self) -> None:
        swarm_root = self.codex_home / "swarm"
        media_root = swarm_root / "proof-media"
        event_root = swarm_root / "proof-events"
        media_root.mkdir(parents=True)
        event_root.mkdir(parents=True)
        media = media_root / "proof.png"
        media.write_bytes(b"\x89PNG\r\n\x1a\nproof")
        digest = hashlib.sha256(media.read_bytes()).hexdigest()
        event = {
            "schema_version": 1,
            "source": "CtrlEvidence",
            "evidence_id": "event-proof",
            "task_id": "task-1",
            "kind": "screenshot",
            "locator": "proof-media/proof.png",
            "caption": "Observed settings screen",
            "claim_limit": "Available for review; acceptance is recorded separately.",
            "digest": digest,
            "size_bytes": media.stat().st_size,
            "media_type": "image/png",
            "disposition": "PENDING",
        }
        (event_root / "event.json").write_text(json.dumps(event), encoding="utf-8")
        store = console.ConsoleStore(self.root / "console" / "events.sqlite3")
        overview = {"nodes": [{"id": "task-1", "project_id": "project:alpha", "virtual": False}]}
        self.assertEqual(store.ingest_proof_events(self.codex_home, overview, now_ms=9), 1)
        item = store.proof_feed(project_id="project:alpha")[0]
        self.assertEqual(item["task_id"], "task-1")
        self.assertEqual(item["disposition"], "PENDING")
        event["evidence_id"] = "outside"
        event["locator"] = "../outside.png"
        (event_root / "outside.json").write_text(json.dumps(event), encoding="utf-8")
        with mock.patch.object(console, "_media_metadata", wraps=console._media_metadata) as metadata:
            self.assertEqual(store.ingest_proof_events(self.codex_home, overview, now_ms=10), 0)
        metadata.assert_not_called()
        self.assertEqual(len(store.proof_feed()), 1)

    def _write_proof_event(
        self,
        evidence_id: str,
        task_id: str,
        *,
        payload: bytes = b"\x89PNG\r\n\x1a\nproof",
        locator_name: str | None = None,
        digest: str | None = None,
    ) -> Path:
        swarm_root = self.codex_home / "swarm"
        media_root = swarm_root / "proof-media"
        event_root = swarm_root / "proof-events"
        media_root.mkdir(parents=True, exist_ok=True)
        event_root.mkdir(parents=True, exist_ok=True)
        media_name = locator_name or f"{evidence_id}.png"
        media = media_root / media_name
        media.write_bytes(payload)
        event = {
            "schema_version": 1,
            "source": "CtrlEvidence",
            "evidence_id": evidence_id,
            "task_id": task_id,
            "kind": "screenshot",
            "locator": f"proof-media/{media_name}",
            "caption": f"Proof {evidence_id}",
            "claim_limit": "Available for review; acceptance is recorded separately.",
            "digest": digest or hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
            "media_type": "image/png",
            "disposition": "PENDING",
        }
        event_path = event_root / f"{evidence_id}.json"
        event_path.write_text(json.dumps(event), encoding="utf-8")
        return event_path

    def test_proof_feed_reconciles_fresh_and_same_state_restart_without_churn(self) -> None:
        self._write_proof_event("restart-proof", "restart-task")
        state_path = self.root / "console" / "restart.sqlite3"
        overview = {"nodes": [{"id": "restart-task", "project_id": "project:restart", "virtual": False}]}
        first_app = console.App(self.codex_home, self.config, state_path)
        with mock.patch.object(first_app, "_host_overview", return_value=overview):
            first = first_app.proof_feed(project_id="project:restart")
        self.assertEqual([item["evidence_id"] for item in first], ["restart-proof"])
        with closing(sqlite3.connect(state_path)) as connection:
            before = connection.execute(
                "SELECT registered_at_ms, updated_at_ms, observed_at_ms FROM proof_media "
                "JOIN proof_event_receipts USING(evidence_id) WHERE evidence_id='restart-proof'"
            ).fetchone()

        restarted_app = console.App(self.codex_home, self.config, state_path)
        with mock.patch.object(restarted_app, "_host_overview", return_value=overview), mock.patch.object(
            restarted_app.store,
            "reconcile_proof_events",
            wraps=restarted_app.store.reconcile_proof_events,
        ) as reconcile:
            second = restarted_app.proof_feed(project_id="project:restart")
            third = restarted_app.proof_feed(project_id="project:restart")
        self.assertEqual(second, third)
        self.assertEqual(reconcile.call_count, 2)
        with closing(sqlite3.connect(state_path)) as connection:
            after = connection.execute(
                "SELECT registered_at_ms, updated_at_ms, observed_at_ms FROM proof_media "
                "JOIN proof_event_receipts USING(evidence_id) WHERE evidence_id='restart-proof'"
            ).fetchone()
        self.assertEqual(before, after)

    def test_proof_feed_rehydrates_missing_row_despite_imported_receipt(self) -> None:
        self._write_proof_event("rehydrate-proof", "rehydrate-task")
        state_path = self.root / "console" / "rehydrate.sqlite3"
        overview = {"nodes": [{"id": "rehydrate-task", "project_id": "project:rehydrate", "virtual": False}]}
        app = console.App(self.codex_home, self.config, state_path)
        with mock.patch.object(app, "_host_overview", return_value=overview):
            self.assertEqual(len(app.proof_feed()), 1)
        with closing(sqlite3.connect(state_path)) as connection:
            connection.execute("DELETE FROM proof_media WHERE evidence_id='rehydrate-proof'")
            connection.commit()

        restarted = console.App(self.codex_home, self.config, state_path)
        with mock.patch.object(restarted, "_host_overview", return_value=overview):
            self.assertEqual([item["evidence_id"] for item in restarted.proof_feed()], ["rehydrate-proof"])

    def test_proof_event_legacy_receipt_rehydrates_missing_row_and_binds_once(self) -> None:
        self._write_proof_event("legacy-proof", "legacy-task")
        state_path = self.root / "console" / "legacy.sqlite3"
        overview = {"nodes": [{"id": "legacy-task", "project_id": "project:legacy", "virtual": False}]}
        store = console.ConsoleStore(state_path)
        self.assertEqual(store.reconcile_proof_events(self.codex_home, overview, now_ms=1)["imported"], 1)
        with closing(sqlite3.connect(state_path)) as connection:
            connection.execute(
                "UPDATE proof_event_receipts SET event_digest=NULL, task_id=NULL, project_id=NULL, media_digest=NULL"
            )
            connection.execute("DELETE FROM proof_media WHERE evidence_id='legacy-proof'")
            connection.commit()

        migrated = console.ConsoleStore(state_path)
        first = migrated.reconcile_proof_events(self.codex_home, overview, now_ms=2)
        second = migrated.reconcile_proof_events(self.codex_home, overview, now_ms=3)
        self.assertEqual((first["imported"], second["duplicates"]), (1, 1))
        self.assertEqual([item["evidence_id"] for item in migrated.proof_feed()], ["legacy-proof"])
        with closing(sqlite3.connect(state_path)) as connection:
            row = connection.execute(
                "SELECT event_digest, task_id, project_id, media_digest, observed_at_ms "
                "FROM proof_event_receipts WHERE event_name='legacy-proof.json'"
            ).fetchone()
        self.assertTrue(all(row[index] for index in range(4)))
        self.assertEqual(row[4], 1)

    def test_proof_feed_retries_late_host_observation_without_event_rewrite(self) -> None:
        event_path = self._write_proof_event("late-proof", "late-task")
        original_stat = event_path.stat()
        app = console.App(self.codex_home, self.config, self.root / "console" / "late.sqlite3")
        empty = {"nodes": []}
        observed = {"nodes": [{"id": "late-task", "project_id": "project:late", "virtual": False}]}
        with mock.patch.object(app, "_host_overview", side_effect=[empty, observed]):
            self.assertEqual(app.proof_feed(), [])
            self.assertEqual([item["evidence_id"] for item in app.proof_feed()], ["late-proof"])
        current_stat = event_path.stat()
        self.assertEqual((current_stat.st_mtime_ns, current_stat.st_size), (original_stat.st_mtime_ns, original_stat.st_size))

    def test_proof_feed_retries_transient_store_failure_without_event_rewrite(self) -> None:
        event_path = self._write_proof_event("retry-proof", "retry-task")
        original_stat = event_path.stat()
        app = console.App(self.codex_home, self.config, self.root / "console" / "retry.sqlite3")
        overview = {"nodes": [{"id": "retry-task", "project_id": "project:retry", "virtual": False}]}
        reconcile = app.store.reconcile_proof_events
        calls = 0

        def flaky_reconcile(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise sqlite3.OperationalError("transient lock")
            return reconcile(*args, **kwargs)

        with mock.patch.object(app, "_host_overview", return_value=overview), mock.patch.object(
            app.store, "reconcile_proof_events", side_effect=flaky_reconcile
        ):
            self.assertEqual(app.proof_feed(), [])
            self.assertEqual([item["evidence_id"] for item in app.proof_feed()], ["retry-proof"])
        current_stat = event_path.stat()
        self.assertEqual(calls, 2)
        self.assertEqual((current_stat.st_mtime_ns, current_stat.st_size), (original_stat.st_mtime_ns, original_stat.st_size))

    def test_proof_reconciliation_dedupes_and_rejects_conflicting_or_changed_media(self) -> None:
        original = self._write_proof_event("shared-proof", "task-a")
        self._write_proof_event("changed-proof", "task-a", digest="0" * 64)
        store = console.ConsoleStore(self.root / "console" / "dedupe.sqlite3")
        overview = {"nodes": [{"id": "task-a", "project_id": "project:a", "virtual": False}]}
        result = store.reconcile_proof_events(self.codex_home, overview, now_ms=10)
        self.assertEqual([item["evidence_id"] for item in store.proof_feed()], ["shared-proof"])
        self.assertEqual(result["rejected"], 1)
        with closing(sqlite3.connect(store.path)) as connection:
            connection.execute("UPDATE proof_media SET project_id='project:other' WHERE evidence_id='shared-proof'")
            connection.commit()
        original.touch()
        conflict = store.reconcile_proof_events(self.codex_home, overview, now_ms=11)
        self.assertGreaterEqual(conflict["rejected"], 1)
        self.assertEqual(len(store.proof_feed()), 1)

    def test_proof_event_filename_binding_rejects_content_or_identity_change(self) -> None:
        event_path = self._write_proof_event("immutable-proof", "task-a")
        store = console.ConsoleStore(self.root / "console" / "immutable.sqlite3")
        overview = {"nodes": [
            {"id": "task-a", "project_id": "project:a", "virtual": False},
            {"id": "task-b", "project_id": "project:b", "virtual": False},
        ]}
        self.assertEqual(store.reconcile_proof_events(self.codex_home, overview, now_ms=10)["imported"], 1)
        with closing(sqlite3.connect(store.path)) as connection:
            before = connection.execute(
                "SELECT * FROM proof_event_receipts WHERE event_name='immutable-proof.json'"
            ).fetchone()

        event = json.loads(event_path.read_text(encoding="utf-8"))
        event["caption"] = "Proof immutable-proog"
        event_path.write_text(json.dumps(event), encoding="utf-8")
        changed_content = store.reconcile_proof_events(self.codex_home, overview, now_ms=11)
        self.assertEqual(changed_content["rejected"], 1)

        event["task_id"] = "task-b"
        event["evidence_id"] = "rebound-proof"
        event_path.write_text(json.dumps(event), encoding="utf-8")
        changed_identity = store.reconcile_proof_events(self.codex_home, overview, now_ms=12)
        self.assertEqual(changed_identity["rejected"], 1)
        with closing(sqlite3.connect(store.path)) as connection:
            after = connection.execute(
                "SELECT * FROM proof_event_receipts WHERE event_name='immutable-proof.json'"
            ).fetchone()
        self.assertEqual(before, after)
        self.assertEqual([item["evidence_id"] for item in store.proof_feed()], ["immutable-proof"])

    def test_proof_reconciliation_retries_missing_media_and_preserves_project_privacy(self) -> None:
        missing = self._write_proof_event("missing-proof", "task-a")
        missing_payload = json.loads(missing.read_text(encoding="utf-8"))
        (self.codex_home / "swarm" / missing_payload["locator"]).unlink()
        self._write_proof_event("alpha-proof", "task-a")
        self._write_proof_event("beta-proof", "task-b")
        store = console.ConsoleStore(self.root / "console" / "privacy.sqlite3")
        overview = {"nodes": [
            {"id": "task-a", "project_id": "project:alpha", "virtual": False},
            {"id": "task-b", "project_id": "project:beta", "virtual": False},
        ]}
        result = store.reconcile_proof_events(self.codex_home, overview, now_ms=12)
        self.assertGreaterEqual(result["retryable"], 1)
        self.assertEqual([item["evidence_id"] for item in store.proof_feed(project_id="project:alpha")], ["alpha-proof"])
        self.assertEqual([item["evidence_id"] for item in store.proof_feed(task_id="task-b")], ["beta-proof"])
        self.assertNotIn("missing-proof", {item["evidence_id"] for item in store.proof_feed()})

    def test_proof_reconciliation_rejects_private_payload_fields(self) -> None:
        event_path = self._write_proof_event("private-proof", "private-task")
        event = json.loads(event_path.read_text(encoding="utf-8"))
        event["prompt"] = "must not be stored"
        event_path.write_text(json.dumps(event), encoding="utf-8")
        store = console.ConsoleStore(self.root / "console" / "private.sqlite3")
        overview = {"nodes": [{"id": "private-task", "project_id": "project:private", "virtual": False}]}
        result = store.reconcile_proof_events(self.codex_home, overview, now_ms=13)
        self.assertEqual(result["rejected"], 1)
        self.assertEqual(store.proof_feed(), [])
        with closing(sqlite3.connect(store.path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM proof_media").fetchone()[0], 0)

    def test_proof_event_scan_is_bounded_fair_and_restart_safe(self) -> None:
        for index in range(5):
            self._write_proof_event(f"bounded-{index}", "bounded-task")
        overview = {"nodes": [{"id": "bounded-task", "project_id": "project:bounded", "virtual": False}]}
        state_path = self.root / "console" / "bounded.sqlite3"
        app = console.App(self.codex_home, self.config, state_path)
        with mock.patch.object(console, "MAX_PROOF_EVENT_FILES", 2), mock.patch.object(app, "_host_overview", return_value=overview):
            first = app._ingest_proof_events_if_changed()
        self.assertEqual(first["capped"], 1)
        self.assertEqual(first["enumerated"], 3)
        self.assertEqual(len(app.store.proof_feed()), 0)

        restarted = console.App(self.codex_home, self.config, state_path)
        with mock.patch.object(console, "MAX_PROOF_EVENT_FILES", 2), mock.patch.object(
            restarted, "_host_overview", return_value=overview
        ):
            passes = [restarted._ingest_proof_events_if_changed() for _ in range(64)]
        self.assertTrue(all(result["enumerated"] <= 3 for result in passes))
        self.assertEqual(len(restarted.store.proof_feed()), 5)
        self.assertEqual(restarted._ingest_proof_events_if_changed()["imported"], 0)

        event_root = self.codex_home / "swarm" / "proof-events"
        for index in range(5, 1025):
            (event_root / f"bounded-{index:04d}.json").write_text("{}", encoding="utf-8")
        measured = console.ConsoleStore(self.root / "console" / "measured.sqlite3")
        with mock.patch.object(console, "MAX_PROOF_EVENT_FILES", 1024), mock.patch.object(
            Path, "iterdir", side_effect=AssertionError("full directory traversal is forbidden")
        ):
            paths, capped, enumerated, _ = measured._bounded_proof_event_paths(event_root)
        self.assertEqual(paths, [])
        self.assertTrue(capped)
        self.assertEqual(enumerated, 1025)

        target = "bounded-1024.json"
        seen_target = False
        enumeration_counts: list[int] = []
        for pass_index in range(128):
            if pass_index == 12:
                measured = console.ConsoleStore(measured.path)
            with mock.patch.object(console, "MAX_PROOF_EVENT_FILES", 1024), mock.patch.object(
                Path, "iterdir", side_effect=AssertionError("full directory traversal is forbidden")
            ):
                paths, _, enumerated, queue = measured._bounded_proof_event_paths(event_root)
            enumeration_counts.append(enumerated)
            measured._set_proof_event_scan_queue(queue)
            if target in {path.name for path in paths}:
                seen_target = True
                break
        self.assertTrue(seen_target)
        self.assertTrue(all(count <= 1025 for count in enumeration_counts))

    def test_proof_event_deleted_or_renamed_source_does_not_rebind_receipt(self) -> None:
        event_path = self._write_proof_event("rename-proof", "rename-task")
        store = console.ConsoleStore(self.root / "console" / "rename.sqlite3")
        overview = {"nodes": [{"id": "rename-task", "project_id": "project:rename", "virtual": False}]}
        self.assertEqual(store.reconcile_proof_events(self.codex_home, overview, now_ms=20)["imported"], 1)
        renamed = event_path.with_name("renamed.json")
        event_path.rename(renamed)
        result = store.reconcile_proof_events(self.codex_home, overview, now_ms=21)
        self.assertEqual(result["rejected"], 1)
        renamed.unlink()
        store.reconcile_proof_events(self.codex_home, overview, now_ms=22)
        self.assertEqual([item["evidence_id"] for item in store.proof_feed()], ["rename-proof"])
        with closing(sqlite3.connect(store.path)) as connection:
            rows = connection.execute(
                "SELECT event_name, status FROM proof_event_receipts ORDER BY event_name"
            ).fetchall()
        self.assertEqual(rows, [("rename-proof.json", "IMPORTED"), ("renamed.json", "REJECTED")])

    def test_clear_history_removes_proof_files_and_prevents_reimport(self) -> None:
        swarm_root = self.codex_home / "swarm"
        media_root = swarm_root / "proof-media"
        event_root = swarm_root / "proof-events"
        media_root.mkdir(parents=True)
        event_root.mkdir(parents=True)
        media = media_root / "proof.png"
        media.write_bytes(b"\x89PNG\r\n\x1a\nproof")
        digest = hashlib.sha256(media.read_bytes()).hexdigest()
        (event_root / "event.json").write_text(json.dumps({
            "schema_version": 1, "source": "CtrlEvidence", "evidence_id": "clear-proof",
            "task_id": "task", "kind": "screenshot", "locator": "proof-media/proof.png",
            "caption": "Task proof", "claim_limit": "Available for review.", "digest": digest,
            "size_bytes": media.stat().st_size, "media_type": "image/png", "disposition": "PENDING",
        }), encoding="utf-8")
        app = console.App(self.codex_home, self.config, self.root / "console" / "clear.sqlite3")
        overview = console.build_overview(self.codex_home, self.config)
        self.assertEqual(app.store.ingest_proof_events(self.codex_home, overview, now_ms=1), 1)
        self.assertGreater(app.storage()["proof_bytes"], 0)
        result = app.clear_history()
        self.assertEqual(result["proof"]["files_deleted"], 2)
        self.assertEqual(app.storage()["proof_bytes"], 0)
        self.assertEqual(app.store.proof_feed(), [])
        self.assertEqual(app.store.ingest_proof_events(self.codex_home, overview, now_ms=2), 0)

    def test_proof_event_can_resolve_project_level_task_from_host_metadata(self) -> None:
        database = self.codex_home / "state_5.sqlite"
        project_root = str(self.root / "flowwweb" / "swarm")
        self._add_host_project("project:host-swarm", "swarm", project_root)
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "INSERT INTO threads(id, title, cwd, archived, git_origin_url) VALUES (?, ?, ?, ?, ?)",
                ("project-task", "Project task", project_root, 0, ""),
            )
            connection.commit()
        finally:
            connection.close()
        self.assertEqual(console.observed_task_project_id(self.codex_home, "project-task"), "project:host-swarm")
        self.assertIsNone(console.observed_task_project_id(self.codex_home, "missing"))

    @staticmethod
    def _health_sample(*, cpu: float = 10.0, memory: float = 20.0, free_bytes: int = 20 * 1024**3) -> dict:
        return {
            "sampled_at_ms": 1,
            "cpu": {"available": True, "percent": cpu, "source": "test"},
            "memory": {"available": True, "percent": memory, "used_bytes": 1, "total_bytes": 2, "source": "test"},
            "disks": [{"mount": "C:\\", "free_bytes": free_bytes, "total_bytes": 30 * 1024**3, "percent": 30, "available": True}],
            "docker": {"available": False, "status": "unavailable"},
            "network": {"available": False, "source": "test"},
            "console_storage": {"db_bytes": 1, "wal_bytes": 0, "shm_bytes": 0, "log_bytes": 0},
        }

    def test_diagnostics_preserve_independent_sources_and_report_partial_freshness(self) -> None:
        now_ms = 2_000_000_000_000
        psutil_stub = SimpleNamespace(
            cpu_percent=lambda interval=None: 37.5,
            virtual_memory=lambda: SimpleNamespace(percent=62.0, used=620, total=1_000),
            net_io_counters=lambda: (_ for _ in ()).throw(OSError("network counters unavailable")),
        )
        docker_unavailable = {
            "available": False,
            "status": "unavailable",
            "container_count": 0,
            "source": "docker_cli_read_only",
            "unavailable_reason": "Docker CLI is not available.",
            "recommended_action": "Keep container metrics unavailable.",
        }
        collector = console.DiagnosticsCollector(self.codex_home, self.root / "console" / "state.sqlite3", now_fn=lambda: now_ms / 1000)
        with mock.patch.dict(sys.modules, {"psutil": psutil_stub}), mock.patch.object(
            console.DiagnosticsCollector, "_docker_status", return_value=docker_unavailable,
        ):
            sample = collector.collect()

        self.assertEqual(sample["cpu"]["percent"], 37.5)
        self.assertEqual(sample["memory"]["percent"], 62.0)
        self.assertFalse(sample["network"]["available"])
        self.assertEqual(sample["cpu"]["source"], "psutil")
        self.assertEqual(sample["cpu"]["observed_at_ms"], now_ms)
        self.assertTrue(sample["disks"][0]["available"])
        response = console._diagnostic_record_for_response(
            {"sampled_at_ms": now_ms, "health_state": "HEALTHY", "reasons": [], "payload": sample},
            now_ms + 60_000,
        )
        self.assertEqual(response["source_timestamp_ms"], now_ms)
        self.assertEqual(response["freshness"]["state"], "fresh")
        self.assertEqual(response["payload"]["availability"]["status"], "partial")
        self.assertEqual(
            {item["group"] for item in response["payload"]["availability"]["unavailable_groups"]},
            {"containers", "network"},
        )

    def test_diagnostics_no_sample_is_grouped_and_explicitly_unverified(self) -> None:
        app = console.App(self.codex_home, self.config)
        result = app.diagnostics()
        latest = result["latest"]
        self.assertEqual(latest["health_state"], "UNKNOWN")
        self.assertEqual(latest["freshness"]["state"], "no_data")
        self.assertEqual(latest["payload"]["availability"]["status"], "no_data")
        self.assertEqual(latest["payload"]["availability"]["unavailable_groups"][0]["group"], "host")
        self.assertFalse(result["usage_consumed"])

    def test_health_contract_is_typed_local_and_reports_repair_policy_without_dispatch(self) -> None:
        app = console.App(self.codex_home, self.config)
        contract = app.health_contract()
        checks = {check["id"]: check for check in contract["checks"]}
        expected = {
            "process.source_mirror_parity",
            "process.listener_package_parity",
            "project.roster_root_binding",
            "projection.ctrl_activity",
            "host.thread_freshness_parent_edges",
            "ledger.cursor_freshness",
            "asset.evidence_store",
            "config.schema_compatibility_redaction",
            "api.health_endpoint_response",
            "refresh.last_success",
        }
        self.assertEqual(set(checks), expected)
        self.assertTrue(all(check["status"] in console.HEALTH_CHECK_STATUSES for check in checks.values()))
        self.assertTrue(all(isinstance(check["observed_at_ms"], int) for check in checks.values()))
        self.assertTrue(all(pointer.startswith("local:") for check in checks.values() for pointer in check["evidence"]))
        self.assertNotIn("C:\\", json.dumps(contract))
        self.assertEqual(contract["codex_connection"]["status"], "CONNECTED")
        self.assertEqual(contract["codex_connection"]["source"], "local:codex-state-db+host-project-roster")
        self.assertEqual(contract["codex_connection"]["connection_scope"], "LOCAL_METADATA_SNAPSHOT")
        self.assertEqual(contract["codex_connection"]["transport_status"], "UNVERIFIED")
        self.assertEqual(contract["codex_connection"]["project_count"], 1)
        self.assertEqual(contract["codex_connection"]["observed_host_tasks"], 5)
        self.assertEqual(contract["binding_coverage"]["status"], "DEGRADED")
        self.assertEqual(contract["binding_coverage"]["reason"], "No authoritative SWARM bindings")
        self.assertEqual(contract["binding_coverage"]["bound_agents"], 0)
        self.assertEqual(contract["binding_coverage"]["independent_tasks"], 5)
        self.assertFalse(contract["binding_coverage"]["execution_authority"])
        self.assertIn("No authoritative SWARM bindings", contract["binding_coverage"]["actionable_repair"])
        self.assertEqual(contract["repair_policy"]["key"], "monitoring.auto_health_enabled")
        self.assertEqual(contract["repair_policy"]["label"], "Automatic health review requests")
        self.assertEqual(contract["repair_policy"]["state"], "KNOWN")
        self.assertEqual(contract["repair_policy"]["status"], "OFF")
        self.assertFalse(contract["repair_policy"]["enabled"])
        self.assertEqual(contract["repair_policy"]["dispatch"], "disabled")
        self.assertEqual(contract["repair_policy"]["automatic_request_mode"], "none")
        self.assertIn("deterministic health checks remain active", contract["repair_policy"]["reason"])

        console.update_config(self.config, {"monitoring.auto_health_enabled": True})
        enabled_policy = console.App(self.codex_home, self.config).health_contract()["repair_policy"]
        self.assertEqual(enabled_policy["key"], "monitoring.auto_health_enabled")
        self.assertEqual(enabled_policy["status"], "ON")
        self.assertTrue(enabled_policy["enabled"])
        self.assertEqual(enabled_policy["automatic_request_mode"], "bounded_existing_health_requests")
        self.assertEqual(enabled_policy["dispatch"], "disabled")
        self.assertIn("not an allowlisted low-risk repair executor", enabled_policy["reason"])

        before_requests = app.store.health_requests()
        prepared = app.prepare_health_repair(
            ["process.listener_package_parity"],
            scope="all",
            acknowledge=False,
            dry_run=True,
        )
        request = prepared["request"]
        self.assertFalse(request["deduplicated"])
        self.assertFalse(request["persistent"])
        self.assertEqual(request["status"], "PREVIEW")
        self.assertEqual(request["payload"]["persistence"], "preview_only")
        self.assertEqual(request["payload"]["check_ids"], ["process.listener_package_parity"])
        self.assertFalse(request["payload"]["auto_dispatch"])
        self.assertEqual(request["payload"]["dispatch_status"], "NOT_DISPATCHED")
        replay = app.prepare_health_repair(
            ["process.listener_package_parity"],
            scope="all",
            acknowledge=False,
            dry_run=True,
        )
        self.assertFalse(replay["request"]["deduplicated"])
        self.assertEqual(replay["request"]["request_id"], request["request_id"])
        self.assertFalse(replay["request"]["persistent"])
        self.assertEqual(app.store.health_requests(), before_requests)

        with self.assertRaisesRegex(console.ConsoleError, "requires acknowledgement"):
            app.prepare_health_repair(
                ["process.listener_package_parity"],
                scope="all",
                acknowledge=False,
                dry_run=False,
            )

        persisted = app.prepare_health_repair(
            ["process.listener_package_parity"],
            scope="all",
            acknowledge=True,
            dry_run=False,
        )
        self.assertTrue(persisted["request"]["persistent"])
        self.assertEqual(persisted["request"]["status"], "OPEN")
        self.assertEqual(len(app.store.health_requests(status="OPEN")), 1)

    def test_health_source_mirror_parity_requires_two_identities(self) -> None:
        app = console.App(self.codex_home, self.config)
        source_server, mirror_server = console._server_identity_paths()
        self.assertNotEqual(source_server, mirror_server)
        self.assertTrue(source_server.is_file())
        self.assertTrue(mirror_server.is_file())
        checks = {check["id"]: check for check in app.health_contract()["checks"]}
        self.assertEqual(checks["process.source_mirror_parity"]["status"], "PASS")
        self.assertTrue(checks["process.source_mirror_parity"]["details"]["independent_identities"])

        installed_server = self.root / "installed-package" / "console" / "server.py"
        installed_server.parent.mkdir(parents=True)
        installed_server.write_bytes(source_server.read_bytes())
        with mock.patch.object(console, "__file__", str(installed_server)):
            installed_checks = {check["id"]: check for check in app.health_contract()["checks"]}
        installed_parity = installed_checks["process.source_mirror_parity"]
        self.assertEqual(installed_parity["status"], "UNKNOWN")
        self.assertEqual(installed_parity["details"]["source_mirror"], "unavailable")

    def test_health_contract_fail_closes_missing_project_inventory_and_keeps_local_checks(self) -> None:
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DROP TABLE projects")
            connection.commit()
        app = console.App(self.codex_home, self.config)
        contract = app.health_contract()
        checks = {check["id"]: check for check in contract["checks"]}
        self.assertEqual(checks["project.roster_root_binding"]["status"], "UNKNOWN")
        self.assertEqual(checks["projection.ctrl_activity"]["status"], "UNKNOWN")
        self.assertEqual(contract["codex_connection"]["status"], "DEGRADED")
        self.assertEqual(contract["binding_coverage"]["status"], "UNAVAILABLE")
        self.assertIsNone(contract["binding_coverage"]["project_count"])
        self.assertIn(checks["asset.evidence_store"]["status"], {"PASS", "FAIL"})
        self.assertFalse(app.health_settings()["auto_repair"]["enabled"])

    def test_health_contract_reports_unavailable_when_codex_state_cannot_be_read(self) -> None:
        app = console.App(self.codex_home, self.config)
        with mock.patch.object(app, "_host_project_records", side_effect=console.ConsoleError("missing host DB")), mock.patch.object(
            app, "_host_overview", side_effect=console.ConsoleError("missing host DB"),
        ):
            contract = app.health_contract()
        self.assertEqual(contract["codex_connection"]["status"], "UNAVAILABLE")
        self.assertIsNone(contract["codex_connection"]["project_count"])
        self.assertIsNone(contract["codex_connection"]["observed_host_tasks"])
        self.assertEqual(contract["binding_coverage"]["status"], "UNAVAILABLE")
        self.assertIsNone(contract["binding_coverage"]["bound_agents"])
        self.assertIsNone(contract["binding_coverage"]["observed_at_ms"])
        self.assertIn("Restore", contract["codex_connection"]["actionable_repair"])

    def test_health_summaries_fail_closed_for_partial_stale_and_unreconciled_inputs(self) -> None:
        app = console.App(self.codex_home, self.config)
        roster = app._host_project_records()
        with mock.patch.object(app, "_host_project_records", return_value=("PARTIAL", *roster[1:])):
            partial_roster = app.health_contract()
        self.assertEqual(partial_roster["binding_coverage"]["status"], "DEGRADED")
        self.assertEqual(partial_roster["binding_coverage"]["reason"], "Project roster is partial")
        self.assertIn("complete canonical project roster", partial_roster["binding_coverage"]["actionable_repair"])

        independent = [{} for _ in range(5)]
        with mock.patch.object(app, "_topology_projection", return_value={
            "state": "PARTIAL", "reason": "MISSING_OR_CONFLICTING_BINDING",
            "nodes": [], "independent_nodes": independent,
        }):
            partial_topology = app.health_contract()
        self.assertEqual(partial_topology["binding_coverage"]["status"], "DEGRADED")
        self.assertEqual(partial_topology["binding_coverage"]["reason"], "MISSING_OR_CONFLICTING_BINDING")
        self.assertIn("missing or conflicting retained bindings", partial_topology["binding_coverage"]["actionable_repair"])

        with mock.patch.object(app, "_topology_projection", return_value={
            "state": "KNOWN", "nodes": [], "independent_nodes": independent[:-1],
        }):
            mismatch = app.health_contract()
        self.assertEqual(mismatch["binding_coverage"]["reason"], "Binding counts do not reconcile")
        self.assertIn("counts reconcile", mismatch["binding_coverage"]["actionable_repair"])

        with mock.patch.object(app, "_health_contract_status", return_value="PASS"), mock.patch.object(
            app, "_topology_projection", return_value={
                "state": "PARTIAL", "reason": "MISSING_OR_CONFLICTING_BINDING",
                "nodes": [], "independent_nodes": independent,
            },
        ):
            degraded = app.health_contract()
        self.assertEqual(degraded["status"], "WARN")

        stale_overview = app._host_overview()
        stale_overview["generated_at"] = "1970-01-01T00:00:00Z"
        stale = app.health_checks(stale_overview, now_ms=4_000_000)
        self.assertEqual(stale["codex_connection"]["status"], "DEGRADED")
        self.assertEqual(stale["codex_connection"]["observed_at_ms"], 0)

        with mock.patch.object(app, "_topology_projection", side_effect=console.ConsoleError("unavailable")):
            unavailable = app.health_contract()
        self.assertEqual(unavailable["binding_coverage"]["status"], "UNAVAILABLE")
        self.assertEqual(unavailable["status"], "UNKNOWN")
        self.assertEqual(app._health_contract_status([{"status": "WARN"}, {"status": "UNKNOWN"}]), "UNKNOWN")

    def test_health_classification_persistence_sustain_dedupe_and_recovery(self) -> None:
        self.assertEqual(console.assess_health({})["state"], "UNKNOWN")
        self.assertEqual(console.assess_health(self._health_sample())["state"], "HEALTHY")
        path = self.root / "console" / "health.sqlite3"
        store = console.ConsoleStore(path)
        pressured = self._health_sample(free_bytes=4 * 1024**3)
        first = store.record_diagnostics(pressured, now_ms=1_000, auto_enabled=True, sustain_seconds=300, recovery_seconds=600)
        self.assertEqual(first["request_ids"], [])
        second = store.record_diagnostics(pressured, now_ms=301_000, auto_enabled=True, sustain_seconds=300, recovery_seconds=600)
        self.assertEqual(len(second["request_ids"]), 1)
        repeated = store.record_diagnostics(pressured, now_ms=302_000, auto_enabled=True, sustain_seconds=300, recovery_seconds=600)
        self.assertEqual(repeated["request_ids"], second["request_ids"])
        restarted = console.ConsoleStore(path)
        self.assertEqual(len(restarted.health_requests(status="OPEN")), 1)
        recovering = restarted.record_diagnostics(self._health_sample(), now_ms=303_000, auto_enabled=True, sustain_seconds=300, recovery_seconds=600)
        self.assertEqual(recovering["request_ids"], [])
        recovered = restarted.record_diagnostics(self._health_sample(), now_ms=904_000, auto_enabled=True, sustain_seconds=300, recovery_seconds=600)
        self.assertEqual(recovered["request_ids"], [])
        self.assertEqual(restarted.health_requests()[0]["status"], "RECOVERED")
        self.assertEqual(restarted.health_incidents()[0]["state"], "RECOVERED")

    def test_auto_health_off_has_no_request_and_claim_is_single_winner(self) -> None:
        path = self.root / "console" / "health-off.sqlite3"
        store = console.ConsoleStore(path)
        sample = self._health_sample(free_bytes=4 * 1024**3)
        store.record_diagnostics(sample, now_ms=1_000, auto_enabled=False, sustain_seconds=1)
        store.record_diagnostics(sample, now_ms=3_000, auto_enabled=False, sustain_seconds=1)
        self.assertEqual(store.health_requests(), [])
        store.record_diagnostics(sample, now_ms=5_000, auto_enabled=True, sustain_seconds=1)
        request_id = store.health_requests(status="OPEN")[0]["request_id"]
        store.claim_health_request(request_id, now_ms=6_000)
        with self.assertRaises(console.ConsoleConflict):
            store.claim_health_request(request_id, now_ms=7_000)

    def test_diagnostics_reads_are_pure_and_clear_preserves_ctrl_overlay(self) -> None:
        app = console.App(self.codex_home, self.config)
        with mock.patch.object(app, "observe_once", side_effect=AssertionError("usage path")):
            result = app.diagnostics()
            history = app.diagnostics_history()
        self.assertFalse(result["usage_consumed"])
        self.assertEqual(history, [])
        store = console.ConsoleStore(self.root / "console" / "health-clear.sqlite3")
        store.update_ctrl_override("ctrl-1", {"reasoning": "high"}, expected_revision=0, now_ms=1)
        store.record_diagnostics(self._health_sample(), now_ms=1, auto_enabled=False)
        store.clear_history()
        self.assertEqual(store.diagnostics_history(), [])
        self.assertEqual(store.health_incidents(), [])
        self.assertEqual(store.get_ctrl_override("ctrl-1")["revision"], 1)

    def test_ctrl_overlay_requires_revision_and_can_reset_to_global(self) -> None:
        store = console.ConsoleStore(self.root / "console" / "overrides.sqlite3")
        now = int(time.time() * 1000)
        updated = store.update_ctrl_override(
            "ctrl-1", {"model": "gpt-5.6-sol"}, expected_revision=0, now_ms=now
        )
        self.assertEqual(updated["revision"], 1)
        with self.assertRaises(console.ConsoleConflict):
            store.update_ctrl_override("ctrl-1", {"reasoning": "high"}, expected_revision=0, now_ms=now)
        audit = console.App._config_operation_audit(
            action="ctrl_settings_reset",
            operation_id="ctrl-reset-1",
            scope={"type": "ctrl", "ctrl_id": "ctrl-1"},
            expected_revision=1,
            request_digest=console._config_sha256(b"ctrl-settings-reset"),
            new_revision=0,
            changed_paths=["ctrl.model"],
            source_kind="ctrl_settings_overlay",
        )
        self.assertTrue(store.reset_ctrl_override(
            "ctrl-1",
            expected_revision=1,
            operation_id="ctrl-reset-1",
            audit_payload=audit,
            now_ms=now,
        )["reset"])
        self.assertEqual(store.get_ctrl_override("ctrl-1")["revision"], 0)

    def test_valid_config_update_is_validated_and_backed_up(self) -> None:
        result = console.update_config(self.config, {"monitoring.heartbeat_minutes": 45})
        self.assertEqual(result["settings"]["monitoring"]["heartbeat_minutes"], 45)
        self.assertTrue(self.config.with_suffix(".toml.swarm-console.bak").exists())
        self.assertEqual(result["mutation_receipt"]["changed_keys"], ["monitoring.heartbeat_minutes"])

    def test_project_progress_feed_settings_are_server_owned_and_bounded(self) -> None:
        before = console.redacted_config_snapshot(self.config)
        self.assertTrue(before["settings"]["console"]["project_progress_feed_enabled"])
        self.assertEqual(before["settings"]["console"]["project_progress_feed_lines"], 4)
        self.assertIn("console.project_progress_feed_enabled", before["editable"])
        self.assertIn("console.project_progress_feed_lines", before["editable"])
        result = console.update_config(
            self.config,
            {
                "console.project_progress_feed_enabled": False,
                "console.project_progress_feed_lines": 10,
            },
        )
        self.assertFalse(result["settings"]["console"]["project_progress_feed_enabled"])
        self.assertEqual(result["settings"]["console"]["project_progress_feed_lines"], 10)
        self.assertTrue(result["mutation_receipt"]["accepted"])
        self.assertEqual(result["mutation_receipt"]["revision"], result["mutation_receipt"]["config_digest"])
        with self.assertRaisesRegex(console.ConsoleError, "between 1 and 10"):
            console.update_config(self.config, {"console.project_progress_feed_lines": 11})

    def test_project_progress_feed_is_lazy_and_disabled_delivery_does_not_read_ledger(self) -> None:
        app = object.__new__(console.App)
        app.config_path = self.config
        app.progress_ledger = SimpleNamespace()
        snapshot = {
            "project_id": "project-alpha",
            "limit": 4,
            "cursor": {"event_seq": 3, "event_id": "event-3", "event_digest": "a" * 64},
            "items": [],
            "stale_cursor": False,
            "scan_truncated": False,
            "transport": {"snapshot": "available", "incremental": "in_process_event_notification", "http_stream": "UNVERIFIED"},
            "producer": {"status": "typed_runtime_transition_only", "native_host_transport": "UNVERIFIED"},
            "claim_limit": "source only",
        }
        app.progress_ledger.feed_snapshot = mock.Mock(return_value=snapshot)
        feed = app.progress_ledger.feed_snapshot
        with mock.patch.object(app.progress_ledger, "feed_snapshot", feed):
            result = app.project_progress_feed("project-alpha")
        self.assertTrue(result["enabled"])
        self.assertEqual(result["cursor"]["event_seq"], 3)
        self.assertEqual(result["producer"]["native_host_transport"], "UNVERIFIED")
        feed.assert_called_once_with("project-alpha", limit=4, after_cursor=0)

        console.update_config(self.config, {"console.project_progress_feed_enabled": False})
        with mock.patch.object(app.progress_ledger, "feed_snapshot", side_effect=AssertionError("disabled feed read"), create=True):
            disabled = app.project_progress_feed("project-alpha", after_cursor=3)
        self.assertFalse(disabled["enabled"])
        self.assertEqual(disabled["items"], [])

    @staticmethod
    def _auto_decision(ctrl_id: str = "root", project_id: str = "project:alpha") -> dict[str, object]:
        return {
            "ctrl_id": ctrl_id, "project_id": project_id, "goal_id": "goal-auto",
            "task_id": "task", "owner_id": ctrl_id, "request_id": "expected-auto",
            "observed_turn_id": "turn-observed", "decision_digest": "a" * 64,
            "route_digest": "b" * 64, "instruction_digest": "c" * 64,
            "next_operation": "CORRECT-EMPTY-OUTPUT-AND-RETRY-ONCE", "request_bytes": 128,
        }

    @staticmethod
    def _auto_generation() -> ExecutionConfigGeneration:
        return ExecutionConfigGeneration("auto-generation", False, "", "", 1, "host:config:auto")

    @staticmethod
    def _auto_projection(
        *, retry_action: str = "CONTINUE", reason: str = "EMPTY_OUTPUT", event_id: str = "lifecycle-3",
    ) -> dict[str, object]:
        receipt = {
            "receipt_id": "expected-auto", "goal_id": "goal-auto", "task_id": "task",
            "owner_id": "task", "lease_version": 1, "target_id": "artifact-auto",
            "artifact_digest": "e" * 64, "expected_event_kind": "RESULT_PENDING",
            "due_event": "TURN_COMPLETION", "due_generation": 1, "source_cursor": 0,
            "attempted_route_digests": ["b" * 64], "observed_at_ms": 1,
        }
        return {
            "cursor": {"event_seq": 2},
            "expected_receipts": {"expected-auto": {
                "receipt": receipt, "event_seq": 1,
                "result": {
                    "status": "ATTENTION", "reason": reason, "event_id": event_id,
                    "event_digest": "f" * 64, "route_digest": "b" * 64,
                    "retry_action": retry_action,
                },
            }},
        }

    @staticmethod
    def _auto_lifecycle(
        state: str = "STALLED", *, routes: tuple[str, ...] = ("route-a",),
        permitted: tuple[str, ...] = ("route-a", "route-b"), turns: tuple[str, ...] = ("turn-a",),
        sequence: int = 3, release_authority: str | None = None,
        release_receipt_id: str | None = None, request_id: str = "expected-auto",
        stage_id: str = "stage-auto",
    ) -> dict[str, object]:
        event = {
            "schema_version": 1, "record_type": "REQUEST_LIFECYCLE",
            "event_id": f"lifecycle-{sequence}", "dedupe_key": f"lifecycle-dedupe-{sequence}",
            "request_id": request_id, "stage_id": stage_id, "parent_event_id": None,
            "envelope_digest": "1" * 64, "lifecycle_state": state,
            "record": {
                "id": request_id, "goal_id": "goal-auto", "task_id": "task",
                "next_due_event": "provider or user release",
            },
            "route_receipt_ids": list(routes), "permitted_route_ids": list(permitted),
            "failed_goal_turn_receipt_ids": list(turns), "release_authority": release_authority,
            "release_receipt_id": release_receipt_id, "release_issued_at_ms": sequence if release_receipt_id else None,
        }
        return {
            "event_seq": sequence, "event_digest": hashlib.sha256(str(sequence).encode()).hexdigest(),
            "event": event, "_record_type": "REQUEST_LIFECYCLE", "_event": None,
        }

    def _auto_ledger(self, projection: dict[str, object], *records: dict[str, object]):
        return SimpleNamespace(
            replay=mock.Mock(return_value=projection),
            _bounded_tail_records=mock.Mock(return_value=(list(records), False)),
        )

    def test_auto_defaults_off_and_command_replay_restart_and_safe_disable_are_durable(self) -> None:
        path = self.root / "console" / "auto-state.sqlite3"
        store = console.ConsoleStore(path)
        self.assertFalse(store.auto_status("root", "project:alpha")["enabled"])
        self.assertEqual(store.enabled_auto_states(), [])

        enabled = store.set_auto("root", "project:alpha", enabled=True, request_id="enable-1", now_ms=1)
        self.assertTrue(enabled["enabled"])
        replay = store.set_auto("root", "project:alpha", enabled=True, request_id="enable-1", now_ms=2)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["revision"], 1)
        with self.assertRaises(console.ConsoleConflict):
            store.set_auto("root", "project:alpha", enabled=False, request_id="enable-1", now_ms=3)

        claim = store.claim_auto_dispatch(self._auto_decision(), self._auto_generation(), now_ms=4)
        self.assertTrue(claim["claimed"])
        stopping = store.set_auto("root", "project:alpha", enabled=False, request_id="disable-1", now_ms=5)
        self.assertTrue(stopping["in_flight"])
        self.assertTrue(stopping["stop_after_turn"])
        self.assertEqual(stopping["phase"], "STOPPING")
        completed = store.finish_auto_dispatch(
            claim["reservation_id"],
            result=console.AutoBridgeResult(True, "thread-1", "turn-1", "d" * 64, terminal=True, turn_started=True, reachable=True),
            disposition=None, now_ms=6,
        )
        self.assertFalse(completed["enabled"])
        self.assertFalse(completed["in_flight"])
        restarted = console.ConsoleStore(path).auto_status("root", "project:alpha")
        self.assertEqual((restarted["phase"], restarted["revision"]), ("OFF", 2))

        store.set_auto("root", "project:alpha", enabled=True, request_id="enable-2", now_ms=7)
        revision = store.get_ctrl_override("root")["revision"]
        store.update_ctrl_override("root", {"reasoning": "high"}, expected_revision=revision, now_ms=8)
        self.assertTrue(store.auto_status("root", "project:alpha")["enabled"])
        audit = console.App._config_operation_audit(
            action="ctrl_settings_reset",
            operation_id="auto-reset-1",
            scope={"type": "ctrl", "ctrl_id": "root"},
            expected_revision=revision + 1,
            request_digest=console._config_sha256(b"ctrl-settings-reset"),
            new_revision=0,
            changed_paths=["ctrl.reasoning"],
            source_kind="ctrl_settings_overlay",
        )
        store.reset_ctrl_override(
            "root",
            expected_revision=revision + 1,
            operation_id="auto-reset-1",
            audit_payload=audit,
            now_ms=9,
        )
        self.assertTrue(store.auto_status("root", "project:alpha")["enabled"])

    def test_auto_dispatch_is_single_flight_and_idempotent(self) -> None:
        store = console.ConsoleStore(self.root / "console" / "auto-flight.sqlite3")
        store.set_auto("root", "project:alpha", enabled=True, request_id="enable-root", now_ms=1)
        store.set_auto("ctrl-2", "project:alpha", enabled=True, request_id="enable-two", now_ms=2)
        first = store.claim_auto_dispatch(self._auto_decision(), self._auto_generation(), now_ms=3)
        self.assertTrue(first["claimed"])
        second_decision = self._auto_decision("ctrl-2")
        second_decision["decision_digest"] = "d" * 64
        self.assertEqual(store.claim_auto_dispatch(second_decision, self._auto_generation(), now_ms=4)["reason"], "IN_FLIGHT")
        self.assertEqual(store.claim_auto_dispatch(self._auto_decision(), self._auto_generation(), now_ms=5)["reason"], "IN_FLIGHT")
        conflicting = self._auto_decision()
        conflicting["owner_id"] = "other-owner"
        self.assertEqual(store.claim_auto_dispatch(conflicting, self._auto_generation(), now_ms=6)["reason"], "IN_FLIGHT")
        self.assertTrue(console.ConsoleStore(store.path).auto_status("root", "project:alpha")["in_flight"])
        with closing(sqlite3.connect(store.path)) as connection:
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='auto_ctrl_state'").fetchone())

    def test_auto_failure_without_one_disposition_is_strict_noop(self) -> None:
        store = console.ConsoleStore(self.root / "console" / "auto-no-disposition.sqlite3")
        store.set_auto("root", "project:alpha", enabled=True, request_id="enable", now_ms=1)
        claim = store.claim_auto_dispatch(self._auto_decision(), self._auto_generation(), now_ms=2)
        before = store.load_execution_ledger().reservation(claim["reservation_id"]).snapshot()
        with self.assertRaises(console.ConsoleError):
            store.finish_auto_dispatch(
                claim["reservation_id"],
                result=console.AutoBridgeResult(False, failure_kind="TRANSPORT_UNAVAILABLE", transient=True),
                disposition=None, now_ms=3,
            )
        self.assertEqual(store.load_execution_ledger().reservation(claim["reservation_id"]).snapshot(), before)

    def test_auto_candidate_consumes_lifecycle_routes_gates_and_deterministic_rubric(self) -> None:
        app = console.App(self.codex_home, self.config)
        state = {"ctrl_id": "root", "project_id": "project:alpha"}
        overview = console.build_overview(self.codex_home, self.config)
        projection = self._auto_projection(retry_action="REASSESS_ROOT_CAUSE")
        app.progress_ledger = self._auto_ledger(projection, self._auto_lifecycle())
        first = app._auto_candidate(state, overview, projection)
        second = app._auto_candidate(state, overview, projection)
        self.assertEqual(first, second)
        self.assertEqual((first["disposition"]["disposition"], first["disposition"]["next_route"]), ("TRY_ALTERNATE", "route-b"))
        self.assertEqual((first["rubric"]["risk"], first["rubric"]["confidence"]), ("UNKNOWN", "LOW"))
        self.assertEqual(first["rubric"]["proof_strength"], 0)
        retry_projection = self._auto_projection(retry_action="CONTINUE")
        retry = app._auto_candidate(state, overview, retry_projection)
        self.assertEqual(retry["disposition"]["disposition"], "RETRY_SAME")
        self.assertNotEqual(retry["decision_digest"], first["decision_digest"])

        app.progress_ledger = self._auto_ledger(projection, self._auto_lifecycle("KEEP_OUT", routes=(), permitted=(), turns=()))
        waiting = app._auto_candidate(state, overview, projection)
        self.assertEqual(waiting["disposition"]["disposition"], "WAIT_USER")
        self.assertTrue(waiting["rubric"]["user_keep_out"])

        stalled = [
            self._auto_lifecycle(routes=(route,), permitted=("route-a", "route-b", "route-c"), turns=(f"turn-{index}",), sequence=index + 2)
            for index, route in enumerate(("route-a", "route-b", "route-c"), 1)
        ]
        blocked = self._auto_lifecycle(
            "BLOCKED", routes=("route-a", "route-b", "route-c"),
            permitted=("route-a", "route-b", "route-c"), turns=("turn-1", "turn-2", "turn-3"),
            sequence=10, release_authority="provider-owner", release_receipt_id="c" * 64,
        )
        app.progress_ledger = self._auto_ledger(projection, *stalled, blocked)
        terminal = app._auto_candidate(state, overview, projection)
        self.assertEqual(terminal["disposition"]["disposition"], "TERMINAL_BLOCKED")
        self.assertEqual(terminal["disposition"]["responsible_authority"], "provider-owner")

        foreign = self._auto_lifecycle(
            "BLOCKED", routes=("foreign-a", "foreign-b", "foreign-c"),
            permitted=("foreign-a", "foreign-b", "foreign-c"),
            turns=("foreign-turn-a", "foreign-turn-b", "foreign-turn-c"), sequence=20,
            release_authority="foreign-owner", release_receipt_id="d" * 64,
            request_id="expected-foreign", stage_id="stage-foreign",
        )
        app.progress_ledger = self._auto_ledger(
            projection,
            self._auto_lifecycle(permitted=("route-a", "route-b")),
            foreign,
        )
        isolated = app._auto_candidate(state, overview, projection)
        self.assertEqual(
            (isolated["disposition"]["disposition"], isolated["disposition"]["next_route"]),
            ("TRY_ALTERNATE", "route-b"),
        )
        self.assertNotIn("foreign", json.dumps(isolated, sort_keys=True))

    def test_auto_bridge_installed_executable_is_version_and_capability_checked(self) -> None:
        root = self.root / "OpenAI" / "Codex" / "bin"
        current = root / "installed-version" / "codex.exe"
        current.parent.mkdir(parents=True)
        current.touch()
        old = root / "codex.exe"
        old.touch()
        calls = []

        def probe(argv, **kwargs):
            calls.append(argv)
            self.assertEqual(kwargs["timeout"], 5)
            if argv[1:] == ["--version"]:
                return SimpleNamespace(stdout="codex-cli 0.153.4\n" if Path(argv[0]) == current else "codex-cli 0.144.4\n")
            self.assertEqual(argv[1:], ["app-server", "--help"])
            return SimpleNamespace(stdout="--listen stdio://")

        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.root)}), mock.patch.object(console.shutil, "which", return_value=str(old)), mock.patch.object(console.subprocess, "run", side_effect=probe):
            self.assertEqual(console._codex_app_server_executable(), (str(current.resolve()), "0.153.4"))
        self.assertEqual(len(calls), 3)
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.root)}), mock.patch.object(console.shutil, "which", return_value=str(old)), mock.patch.object(console.subprocess, "run", return_value=SimpleNamespace(stdout="codex-cli 0.144.4\n")):
            with self.assertRaisesRegex(OSError, "CODEX_COMPATIBLE_EXECUTABLE_UNAVAILABLE"):
                console._codex_app_server_executable()
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.root)}), mock.patch.object(console.shutil, "which", return_value=None), mock.patch.object(console.subprocess, "run", side_effect=lambda argv, **kw: SimpleNamespace(stdout="codex-cli 0.153.4\n" if argv[1:] == ["--version"] else "unsupported")):
            with self.assertRaisesRegex(OSError, "CODEX_APP_SERVER_CAPABILITY_UNVERIFIED"):
                console._codex_app_server_executable()

    def test_auto_bridge_model_error_is_redacted_and_never_success(self) -> None:
        class Input:
            def write(self, value): pass
            def flush(self): pass
        class Process:
            stdin = Input()
            def __init__(self, line, diagnostic):
                self.stderr = io.StringIO(line + "\n") if diagnostic else io.StringIO()
                self.stdout = io.StringIO() if diagnostic else io.StringIO(line + "\n")
            def poll(self): return None
            def terminate(self): pass
            def wait(self, timeout=None): return 0
            def kill(self): pass
        for diagnostic, line in ((True, "secret-token requires a newer version of Codex"), (False, json.dumps({"method": "error", "params": {"message": "secret-token requires a newer version of Codex"}}))):
            with self.subTest(line=line), mock.patch.object(console.sys, "stderr", new_callable=io.StringIO) as diagnostics:
                drained = threading.Event()
                process = Process(line, diagnostic)
                class DiagnosticStream(io.StringIO):
                    def readline(self, limit):
                        value = super().readline(limit)
                        if not value: drained.set()
                        return value
                process.stderr = DiagnosticStream(line + "\n" if diagnostic else "")
                result = console.CodexStdioBridge(lambda *args, **kwargs: process, executable_resolver=lambda: ("codex-test", "0.153.4")).run(cwd=self.root, instruction="bounded")
                self.assertTrue(drained.wait(2))
                self.assertFalse(result.ok)
                self.assertEqual(result.failure_kind, "TRANSPORT_UNAVAILABLE" if diagnostic else "CODEX_MODEL_REQUIRES_NEWER_CLI")
                self.assertIn("CODEX_MODEL_REQUIRES_NEWER_CLI", diagnostics.getvalue())
                self.assertNotIn("secret-token", diagnostics.getvalue())
        factory = mock.Mock()
        bridge = console.CodexStdioBridge(factory, executable_resolver=mock.Mock(side_effect=OSError("CODEX_COMPATIBLE_EXECUTABLE_UNAVAILABLE")))
        self.assertEqual(bridge.run(cwd=self.root, instruction="bounded").failure_kind, "CODEX_COMPATIBLE_EXECUTABLE_UNAVAILABLE")
        factory.assert_not_called()

    def test_auto_bridge_uses_fixed_argv_jsonl_handshake_and_terminal_event(self) -> None:
        written: list[dict[str, object]] = []
        calls: list[tuple[list[str], dict[str, object]]] = []

        class Input:
            def write(self, value: str) -> None:
                written.append(json.loads(value))

            def flush(self) -> None:
                return None

        class Process:
            stdin = Input()
            stdout = io.StringIO("".join(json.dumps(item) + "\n" for item in (
                {"id": 0, "result": {}},
                {"id": 1, "result": {"thread": {"id": "thread-auto"}}},
                {"method": "item/completed", "params": {"threadId": "thread-auto", "turnId": "turn-auto", "item": {"type": "agentMessage", "text": "bounded result"}}},
                {"method": "turn/completed", "params": {"threadId": "thread-auto", "turnId": "turn-auto", "status": "completed"}},
                {"id": 2, "result": {"turn": {"id": "turn-auto"}}},
            )))

            def poll(self):
                return None

            def terminate(self):
                return None

            def wait(self, timeout=None):
                return 0

            def kill(self):
                return None

        def factory(argv, **kwargs):
            calls.append((argv, kwargs))
            return Process()

        result = console.CodexStdioBridge(factory, executable_resolver=lambda: ("codex-test", "0.153.4")).run(cwd=self.root, instruction="one bounded action")
        self.assertTrue(result.ok)
        self.assertTrue(result.terminal)
        self.assertEqual([item["method"] for item in written], ["initialize", "initialized", "thread/start", "turn/start"])
        self.assertEqual(calls[0][0], ["codex-test", "app-server", "--listen", "stdio://"])
        self.assertFalse(calls[0][1]["shell"])
        self.assertEqual(calls[0][1]["stderr"], console.subprocess.PIPE)
        self.assertEqual(written[-1]["params"]["input"], [{"type": "text", "text": "one bounded action"}])

        Process.stdout = io.StringIO("".join(json.dumps(item) + "\n" for item in (
            {"id": 0, "result": {}},
            {"id": 1, "result": {"thread": {"id": "thread-auto"}}},
            {"id": 2, "result": {"turn": {"id": "turn-auto"}}},
            {"method": "item/completed", "params": {"threadId": "other-thread", "turnId": "other-turn", "item": {"type": "agentMessage", "text": "unrelated result"}}},
            {"method": "turn/completed", "params": {"threadId": "other-thread", "turnId": "other-turn", "status": "completed"}},
            {"method": "turn/completed", "params": {"threadId": "thread-auto", "turnId": "turn-auto", "status": "completed"}},
        )))
        empty = console.CodexStdioBridge(factory, executable_resolver=lambda: ("codex-test", "0.153.4")).run(cwd=self.root, instruction="one bounded action")
        self.assertEqual((empty.ok, empty.terminal, empty.failure_kind), (False, True, "TURN_NO_RESULT"))
        self.assertEqual((empty.thread_id, empty.turn_id), ("thread-auto", "turn-auto"))

        spoofed = [
            {"id": 0, "result": {}},
            {"id": 1, "result": {"thread": {"id": "thread-auto"}}},
            {"id": 2, "result": {"turn": {"id": "turn-auto"}}},
            {"method": "item/completed", "params": {"threadId": "thread-auto", "turnId": "turn-auto", "item": {"type": "agentMessage", "text": "diagnostic not a result"}}},
            {"method": "turn/completed", "params": {"threadId": "thread-auto", "turnId": "turn-auto", "status": "completed"}},
        ]
        for stdout_records, failure in (([], "TRANSPORT_UNAVAILABLE"), (spoofed[:3] + spoofed[-1:], "TURN_NO_RESULT")):
            drained = threading.Event()
            class Diagnostics(io.StringIO):
                def readline(self, limit):
                    value = super().readline(limit)
                    if not value: drained.set()
                    return value
            Process.stderr = Diagnostics("".join(json.dumps(item) + "\n" for item in spoofed))
            Process.stdout = io.StringIO("".join(json.dumps(item) + "\n" for item in stdout_records))
            result = console.CodexStdioBridge(factory, executable_resolver=lambda: ("codex-test", "0.153.4")).run(cwd=self.root, instruction="one bounded action")
            self.assertTrue(drained.wait(2))
            self.assertFalse(result.ok)
            self.assertEqual(result.failure_kind, failure)
            if not stdout_records:
                self.assertEqual((result.thread_id, result.turn_id), ("", ""))

    def test_auto_post_start_disconnect_retains_ids_and_never_starts_a_duplicate_turn(self) -> None:
        written: list[dict[str, object]] = []
        retained: list[tuple[str, str, bool]] = []

        class Input:
            def write(self, value: str) -> None:
                written.append(json.loads(value))
            def flush(self) -> None: return None

        class Process:
            stdin = Input()
            def __init__(self):
                self.stdout = io.StringIO("".join(json.dumps(item) + "\n" for item in (
                    {"id": 0, "result": {}},
                    {"id": 1, "result": {"thread": {"id": "thread-known"}}},
                    {"id": 2, "result": {"turn": {"id": "turn-known"}}},
                )))
            def poll(self): return None
            def terminate(self): return None
            def wait(self, timeout=None): return 0
            def kill(self): return None

        result = console.CodexStdioBridge(lambda *_args, **_kwargs: Process(), executable_resolver=lambda: ("codex-test", "0.153.4")).run(
            cwd=self.root, instruction="bounded", retain_ids=lambda thread, turn, submitted: retained.append((thread, turn, submitted)),
        )
        self.assertFalse(result.ok)
        self.assertEqual((result.thread_id, result.turn_id, result.turn_started), ("thread-known", "turn-known", True))
        self.assertEqual(retained, [("thread-known", "", True), ("thread-known", "turn-known", True)])
        self.assertEqual([item["method"] for item in written].count("turn/start"), 1)

        def refuse_after_start(thread: str, turn: str, submitted: bool) -> None:
            if turn:
                raise console.ConsoleError("journal unavailable")
        failed_retention = console.CodexStdioBridge(lambda *_args, **_kwargs: Process(), executable_resolver=lambda: ("codex-test", "0.153.4")).run(
            cwd=self.root, instruction="bounded", retain_ids=refuse_after_start,
        )
        self.assertEqual((failed_retention.thread_id, failed_retention.turn_id, failed_retention.turn_started), ("thread-known", "turn-known", True))

        class AmbiguousInput(Input):
            def write(self, value: str) -> None:
                super().write(value)
                if json.loads(value).get("method") == "turn/start":
                    raise OSError("delivered write lost its acknowledgement")

        class AmbiguousProcess(Process):
            stdin = AmbiguousInput()

        ambiguous_retained: list[tuple[str, str, bool]] = []
        ambiguous = console.CodexStdioBridge(lambda *_args, **_kwargs: AmbiguousProcess(), executable_resolver=lambda: ("codex-test", "0.153.4")).run(
            cwd=self.root, instruction="bounded",
            retain_ids=lambda thread, turn, submitted: ambiguous_retained.append((thread, turn, submitted)),
        )
        self.assertEqual((ambiguous.thread_id, ambiguous.turn_id, ambiguous.turn_started), ("thread-known", "", True))
        self.assertEqual(ambiguous_retained, [("thread-known", "", True)])
        self.assertEqual([item["method"] for item in written].count("turn/start"), 3)

    def test_auto_bridge_reconciliation_is_read_only_and_classifies_terminal_status(self) -> None:
        written: list[dict[str, object]] = []
        class Input:
            def write(self, value: str) -> None: written.append(json.loads(value))
            def flush(self) -> None: return None
        class Process:
            stdin = Input()
            stdout = io.StringIO("".join(json.dumps(item) + "\n" for item in (
                {"id": 0, "result": {}},
                {"id": 1, "result": {"thread": {"id": "thread-read", "turns": [{"id": "turn-read", "status": "completed", "items": [{"type": "agentMessage", "text": "result"}]}]}}},
            )))
            def poll(self): return None
            def terminate(self): return None
            def wait(self, timeout=None): return 0
            def kill(self): return None
        result = console.CodexStdioBridge(lambda *_args, **_kwargs: Process(), executable_resolver=lambda: ("codex-test", "0.153.4")).reconcile(
            cwd=self.root, thread_id="thread-read", turn_id="turn-read",
        )
        self.assertTrue(result.ok)
        self.assertTrue(result.terminal)
        self.assertEqual([message["method"] for message in written], ["initialize", "initialized", "thread/read"])
        written.clear()
        Process.stdout = io.StringIO("".join(json.dumps(item) + "\n" for item in (
            {"id": 0, "result": {}},
            {"id": 1, "result": {"thread": {"id": "thread-read", "turns": [{"id": "turn-read", "status": "completed"}]}}},
        )))
        inferred = console.CodexStdioBridge(lambda *_args, **_kwargs: Process(), executable_resolver=lambda: ("codex-test", "0.153.4")).reconcile(
            cwd=self.root, thread_id="thread-read", turn_id="",
        )
        self.assertEqual((inferred.ok, inferred.turn_id, inferred.terminal), (False, "turn-read", True))
        self.assertEqual(inferred.failure_kind, "TURN_NO_RESULT")
        self.assertEqual([message["method"] for message in written], ["initialize", "initialized", "thread/read"])

    def test_auto_closed_due_check_is_pure_and_http_status_requires_full_local_auth(self) -> None:
        app = console.App(self.codex_home, self.config)
        app.progress_ledger = SimpleNamespace(replay=mock.Mock(side_effect=AssertionError("closed Auto read Ledger")))
        app.auto_bridge = SimpleNamespace(run=mock.Mock(side_effect=AssertionError("closed Auto launched model")))
        self.assertEqual(app.evaluate_auto_once()["reason"], "AUTO_CLOSED")

        handler = self._handler("127.0.0.1", "127.0.0.1:4788", token="wrong")
        handler.path = "/api/auto?ctrl_id=root&project_id=project%3Aalpha"
        handler._error = mock.Mock()
        handler.do_GET()
        handler._error.assert_called_once_with(
            console.HTTPStatus.FORBIDDEN, "Auto status requires local same-origin authorization",
        )
        docker = self._handler(
            "172.18.0.1", "127.0.0.1:4788", origin="http://127.0.0.1:4788",
        )
        docker.path = "/api/auto"
        docker._error = mock.Mock()
        with mock.patch.dict(console.os.environ, {"SWARM_CONSOLE_DOCKER_LOOPBACK": "1"}):
            docker.do_POST()
        docker._error.assert_called_once_with(
            console.HTTPStatus.FORBIDDEN, "Auto command requires strict loopback authorization",
        )

    def test_auto_waiting_project_does_not_hide_later_project(self) -> None:
        app = object.__new__(console.App)
        states = [{"ctrl_id": name, "project_id": name, "enabled": True, "in_flight": False, "stop_after_turn": False} for name in ("waiting", "next")]
        app.store = SimpleNamespace(enabled_auto_states=lambda: states, retain_auto_control=mock.Mock(return_value=True), auto_status=lambda *_: {})
        app.progress_ledger = SimpleNamespace(replay=lambda: {})
        app._auto_scope = mock.Mock()
        visited = []
        def candidate(state, *_):
            visited.append(state["ctrl_id"])
            if state["ctrl_id"] == "next": return None
            return {"ctrl_id": "waiting", "project_id": "waiting", "decision_digest": "wait", "disposition": {"disposition": "WAIT_USER"}, "rubric": {}}
        app._auto_candidate = candidate
        self.assertEqual(app.evaluate_auto_once({"current": True})["reason"], "WAIT_USER")
        self.assertEqual(visited, ["waiting", "next"])
        app.store.retain_auto_control.assert_called_once()
        visited.clear()
        replay = {key: "bound" for key in ("ctrl_id", "project_id", "goal_id", "task_id", "owner_id", "request_id", "observed_turn_id", "decision_digest", "route_digest", "instruction_digest", "instruction")}
        replay["disposition"] = {"disposition": "RETRY_SAME", "next_operation": "retry"}
        app._auto_candidate = lambda state, *_: (visited.append(state["ctrl_id"]) or (replay if state["ctrl_id"] == "waiting" else None))
        app._auto_project_root = lambda _: self.root
        app._auto_generation = lambda: None
        app.store.claim_auto_dispatch = mock.Mock(return_value={"claimed": False, "reason": "REPLAY"})
        self.assertEqual(app.evaluate_auto_once({"current": True})["reason"], "REPLAY")
        self.assertEqual(visited, ["waiting", "next"])
        app.store.claim_auto_dispatch.assert_called_once()

    def test_auto_due_event_dispatches_once_and_host_completion_is_zero_progress(self) -> None:
        self._confirm_root_ctrl()
        bridge = SimpleNamespace(run=mock.Mock(return_value=console.AutoBridgeResult(
            True, "thread-auto", "turn-auto", "d" * 64, turn_started=True, terminal=True, reachable=True,
        )))
        app = console.App(self.codex_home, self.config, auto_bridge=bridge)
        app.auto_command({
            "command": "ENABLE", "ctrl_id": "root", "project_id": "project:alpha",
            "request_id": "enable-auto",
        })
        projection = self._auto_projection()
        app.progress_ledger = self._auto_ledger(projection, self._auto_lifecycle())
        overview = app._host_overview()
        first = app.evaluate_auto_once(overview)
        self.assertTrue(first["dispatched"])
        self.assertTrue(first["bridge_ok"])
        self.assertEqual(bridge.run.call_count, 1)
        status = app.store.auto_status("root", "project:alpha")
        self.assertEqual(status["phase"], "IDLE")
        with closing(sqlite3.connect(app.store.path)) as connection:
            payload = json.loads(connection.execute(
                "SELECT payload_json FROM execution_event_receipts WHERE event_kind = 'AUTO_OUTCOME'"
            ).fetchone()[0])
        self.assertFalse(payload["material_progress"])
        self.assertEqual(app.evaluate_auto_once(overview)["reason"], "REPLAY")
        self.assertEqual(bridge.run.call_count, 1)

    def test_auto_prestart_transport_retry_reuses_thread_and_is_bounded(self) -> None:
        self._confirm_root_ctrl()
        bridge = SimpleNamespace(run=mock.Mock(side_effect=[
            console.AutoBridgeResult(False, "thread-reuse", failure_kind="TURN_START_FAILED", transient=True),
            console.AutoBridgeResult(True, "thread-reuse", "turn-reuse", "d" * 64, turn_started=True, terminal=True, reachable=True),
        ]))
        app = console.App(self.codex_home, self.config, auto_bridge=bridge)
        app.auto_command({"command": "ENABLE", "ctrl_id": "root", "project_id": "project:alpha", "request_id": "enable-retry"})
        projection = self._auto_projection()
        app.progress_ledger = self._auto_ledger(projection, self._auto_lifecycle())
        with mock.patch.object(console.time, "sleep") as sleep:
            result = app.evaluate_auto_once(app._host_overview())
        self.assertTrue(result["bridge_ok"])
        self.assertEqual(bridge.run.call_count, 2)
        self.assertEqual(bridge.run.call_args_list[1].kwargs["thread_id"], "thread-reuse")
        sleep.assert_called_once()

    def test_auto_restart_reconciles_active_turn_and_authorized_release_recovers_global_lease(self) -> None:
        self._confirm_root_ctrl()
        def uncertain(*, retain_ids, **_kwargs):
            retain_ids("thread-retained", "turn-retained", True)
            return console.AutoBridgeResult(False, "thread-retained", "turn-retained", failure_kind="TRANSPORT_UNAVAILABLE", transient=True, turn_started=True)
        bridge = SimpleNamespace(
            run=mock.Mock(side_effect=uncertain),
            reconcile=mock.Mock(return_value=console.AutoBridgeResult(False, "thread-retained", "turn-retained", failure_kind="TURN_ACTIVE", transient=True, turn_started=True, reachable=True)),
        )
        app = console.App(self.codex_home, self.config, auto_bridge=bridge)
        with self.assertRaises(console.ConsoleError):
            app.auto_command({
                "command": "ENABLE", "ctrl_id": "root", "project_id": "project:missing",
                "request_id": "wrong-project",
            })
        self.assertEqual(app.store.enabled_auto_states(), [])

        app.auto_command({
            "command": "ENABLE", "ctrl_id": "root", "project_id": "project:alpha",
            "request_id": "enable-transient",
        })
        projection = self._auto_projection()
        app.progress_ledger = self._auto_ledger(projection, self._auto_lifecycle())
        first = app.evaluate_auto_once(app._host_overview())
        self.assertTrue(first["state"]["in_flight"])
        restarted = console.App(self.codex_home, self.config, auto_bridge=bridge)
        restarted.progress_ledger = app.progress_ledger
        second = restarted.evaluate_auto_once(restarted._host_overview())
        self.assertEqual(second["reason"], "IN_FLIGHT")
        self.assertEqual((bridge.run.call_count, bridge.reconcile.call_count), (1, 1))
        reservation_id = second["state"]["reservation_id"]
        with self.assertRaises(console.ConsoleConflict):
            restarted.auto_command({
                "command": "RELEASE_UNREACHABLE", "ctrl_id": "root", "project_id": "project:alpha",
                "request_id": "release-while-active", "reservation_id": reservation_id,
                "recovery_authority": "root", "release_condition": "caller assertion is insufficient",
            })
        bridge.reconcile.return_value = console.AutoBridgeResult(
            False, "thread-retained", "turn-retained", failure_kind="TURN_UNREACHABLE",
            transient=True, turn_started=True, reachable=False,
        )
        unreachable = restarted.evaluate_auto_once(restarted._host_overview())
        self.assertEqual(unreachable["reason"], "UNREACHABLE_IN_FLIGHT")
        released = restarted.auto_command({
            "command": "RELEASE_UNREACHABLE", "ctrl_id": "root", "project_id": "project:alpha",
            "request_id": "release-unreachable", "reservation_id": reservation_id,
            "recovery_authority": "root", "release_condition": "host turn is unreachable after retained status read",
        })
        self.assertFalse(released["in_flight"])
        other = self._auto_decision("ctrl-2")
        restarted.store.set_auto("ctrl-2", "project:alpha", enabled=True, request_id="enable-two", now_ms=20)
        self.assertTrue(restarted.store.claim_auto_dispatch(other, self._auto_generation(), now_ms=21)["claimed"])

    def test_auto_restart_terminal_read_releases_lease_without_second_turn_start(self) -> None:
        self._confirm_root_ctrl()
        def uncertain(*, retain_ids, **_kwargs):
            retain_ids("thread-terminal", "turn-terminal", True)
            return console.AutoBridgeResult(False, "thread-terminal", "turn-terminal", failure_kind="TRANSPORT_UNAVAILABLE", transient=True, turn_started=True)
        first_bridge = SimpleNamespace(run=mock.Mock(side_effect=uncertain))
        app = console.App(self.codex_home, self.config, auto_bridge=first_bridge)
        app.auto_command({"command": "ENABLE", "ctrl_id": "root", "project_id": "project:alpha", "request_id": "enable-terminal"})
        projection = self._auto_projection()
        app.progress_ledger = self._auto_ledger(projection, self._auto_lifecycle())
        self.assertTrue(app.evaluate_auto_once(app._host_overview())["state"]["in_flight"])

        read = mock.Mock(return_value=console.AutoBridgeResult(
            True, "thread-terminal", "turn-terminal", "d" * 64,
            turn_started=True, terminal=True, reachable=True,
        ))
        restarted = console.App(self.codex_home, self.config, auto_bridge=SimpleNamespace(reconcile=read))
        restarted.progress_ledger = app.progress_ledger
        result = restarted.evaluate_auto_once(restarted._host_overview())
        self.assertEqual(result["reason"], "RECONCILED")
        self.assertFalse(result["state"]["in_flight"])
        read.assert_called_once()
        self.assertEqual(first_bridge.run.call_count, 1)

    def test_auto_restart_with_submitted_thread_and_no_turn_id_reconciles_or_releases_once(self) -> None:
        self._confirm_root_ctrl()
        def uncertain(*, retain_ids, **_kwargs):
            retain_ids("thread-submitted", "", True)
            return console.AutoBridgeResult(
                False, "thread-submitted", failure_kind="TRANSPORT_UNAVAILABLE",
                transient=True, turn_started=True,
            )
        first_bridge = SimpleNamespace(run=mock.Mock(side_effect=uncertain))
        app = console.App(self.codex_home, self.config, auto_bridge=first_bridge)
        app.auto_command({"command": "ENABLE", "ctrl_id": "root", "project_id": "project:alpha", "request_id": "enable-submitted"})
        projection = self._auto_projection()
        app.progress_ledger = self._auto_ledger(projection, self._auto_lifecycle())
        first = app.evaluate_auto_once(app._host_overview())
        self.assertTrue(first["state"]["in_flight"])
        self.assertEqual((first["state"]["thread_id"], first["state"]["turn_id"]), ("thread-submitted", ""))

        read = mock.Mock(return_value=console.AutoBridgeResult(
            False, "thread-submitted", failure_kind="TURN_NOT_FOUND",
            transient=True, turn_started=True, reachable=True,
        ))
        restarted = console.App(self.codex_home, self.config, auto_bridge=SimpleNamespace(reconcile=read))
        restarted.progress_ledger = app.progress_ledger
        pending = restarted.evaluate_auto_once(restarted._host_overview())
        self.assertEqual(pending["reason"], "UNREACHABLE_IN_FLIGHT")
        read.assert_called_once()
        self.assertEqual(
            (read.call_args.kwargs["thread_id"], read.call_args.kwargs["turn_id"]),
            ("thread-submitted", ""),
        )
        reservation_id = pending["state"]["reservation_id"]
        released = restarted.auto_command({
            "command": "RELEASE_UNREACHABLE", "ctrl_id": "root", "project_id": "project:alpha",
            "request_id": "release-submitted", "reservation_id": reservation_id,
            "recovery_authority": "root", "release_condition": "thread read retained no created turn",
        })
        self.assertFalse(released["in_flight"])
        self.assertEqual(first_bridge.run.call_count, 1)

    def test_auto_health_setting_defaults_off_and_uses_canonical_validator(self) -> None:
        _, effective, _ = console.load_config(self.config)
        self.assertFalse(effective["monitoring"]["auto_health_enabled"])
        result = console.update_config(self.config, {"monitoring.auto_health_enabled": True})
        self.assertTrue(result["settings"]["monitoring"]["auto_health_enabled"])
        with self.assertRaises(console.ConsoleError):
            console.update_config(self.config, {"monitoring.auto_health_enabled": "true"})

    def test_console_exposes_only_the_canonical_automation_mode(self) -> None:
        snapshot = console.redacted_config_snapshot(self.config)
        self.assertEqual(snapshot["settings"]["automation"]["mode"], "standard")
        self.assertIn("automation.mode", snapshot["editable"])
        self.assertNotIn("lifecycle.archive_completed_tasks", snapshot["editable"])
        result = console.update_config(self.config, {"automation.mode": "manual"})
        self.assertEqual(result["settings"]["automation"]["mode"], "manual")
        persisted = self.config.read_text(encoding="utf-8")
        self.assertNotIn("archive_completed_tasks", persisted)
        with self.assertRaises(console.ConsoleError):
            console.update_config(self.config, {"automation.mode": "sometimes"})

    def test_revisioned_global_restore_is_canonical_and_keeps_a_backup(self) -> None:
        console.update_config(self.config, {"monitoring.heartbeat_minutes": 45})
        app = console.App(self.codex_home, self.config)
        projection = app.config_projection({"type": "global"})
        request = {
            "scope": {"type": "global"},
            "expected_revision": projection["revision"],
            "acknowledge": True,
            "operation_id": "global-reset-1",
        }
        result = app.reset_config_source(request)
        replay = app.reset_config_source(request)
        self.assertEqual(result["settings"]["monitoring"]["heartbeat_minutes"], 30)
        self.assertTrue(self.config.with_suffix(".toml.swarm-console.bak").exists())
        self.assertEqual(result["revision"], replay["revision"])
        first_receipt = result["mutation_receipt"]
        replay_receipt = replay["mutation_receipt"]
        for key in (
            "action", "operation_id", "expected_revision", "new_revision", "changed_paths",
            "acknowledged", "audit_event", "source_kind",
        ):
            self.assertEqual(first_receipt[key], replay_receipt[key], key)
        self.assertTrue(first_receipt["changed_paths"])
        self.assertFalse(first_receipt["replayed"])
        self.assertTrue(replay_receipt["replayed"])

    def test_role_icon_controls_preserve_boolean_and_custom_ctrl(self) -> None:
        before = console.redacted_config_snapshot(self.config)
        self.assertIn("role_icons.enabled", before["editable"])
        self.assertIn("role_icons.ctrl", before["editable"])
        result = console.update_config(
            self.config,
            {"role_icons.enabled": False, "role_icons.ctrl": "🕹️"},
        )
        self.assertFalse(result["settings"]["role_icons"]["enabled"])
        self.assertEqual(result["settings"]["role_icons"]["ctrl"], "🕹️")

    def test_formatted_tree_without_controller_scope_is_not_given_a_virtual_ctrl(self) -> None:
        now = 2_000_000_000_000
        connection = sqlite3.connect(self.database)
        connection.executemany(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("specialist-parent", "🧩SPECIALIST - Historical route", "C:/work/beta", now // 1000, now, now, now,
                 "gpt-5.6-sol", "high", 20, 0, "", "main", "", "", "", 0),
                ("specialist", "💻DEV - Historical implementation", "C:/work/beta", now // 1000, now, now, now,
                 "gpt-5.6-luna", "high", 30, 0, "", "main", "", "", "", 0),
            ],
        )
        connection.execute("INSERT INTO thread_spawn_edges VALUES (?,?,?)", ("specialist-parent", "specialist", "open"))
        connection.commit()
        connection.close()

        overview = console.build_overview(self.codex_home, self.config)
        ids = {node["id"] for node in overview["nodes"]}
        self.assertIn("specialist-parent", ids)
        self.assertIn("specialist", ids)
        self.assertTrue(all(
            next(node for node in overview["nodes"] if node["id"] == node_id)["project_binding_state"] == "UNBOUND"
            for node_id in ("specialist-parent", "specialist")
        ))
        self.assertFalse(any(node["virtual"] for node in overview["nodes"]))
        edge = next(link for link in overview["links"] if link["target"] == "specialist")
        self.assertEqual((edge["source"], edge["status"]), ("specialist-parent", "open"))

    def test_standalone_formatted_task_without_spawn_edge_is_visible_at_project_level(self) -> None:
        now = 2_000_000_000_000
        self._add_host_project("project:beta", "beta", "C:/work/beta")
        connection = sqlite3.connect(self.database)
        connection.execute(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("orphan-task", "💻DEV - Title-only task", "C:/work/beta", now // 1000, now, now, now,
             "gpt-5.6-terra", "high", 30, 0, "", "main", "", "", "", 0),
        )
        connection.execute(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("unformatted", "Ordinary user conversation", "C:/work/beta", now // 1000, now, now, now,
             "gpt-5.6-terra", "high", 30, 0, "", "main", "", "", "", 0),
        )
        connection.commit()
        connection.close()

        overview = console.build_overview(self.codex_home, self.config)
        orphan = next(node for node in overview["nodes"] if node["id"] == "orphan-task")
        self.assertEqual(orphan["project"], "beta")
        self.assertIsNone(orphan["parent_id"])
        self.assertEqual(orphan["controller_ids"], [])
        unformatted = next(node for node in overview["nodes"] if node["id"] == "unformatted")
        self.assertEqual((unformatted["project_id"], unformatted["controller_ids"]), (orphan["project_id"], []))
        self.assertFalse(any("orphan-task" in (link["source"], link["target"]) for link in overview["links"]))
        self.assertFalse(any(node["virtual"] for node in overview["nodes"]))
        self.assertEqual(next(project for project in overview["projects"] if project["id"] == orphan["project_id"])["nodes"], 2)

    def test_health_copy_is_product_facing_without_a_watchdog_surface(self) -> None:
        app = (console.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("function renderSystemHealth()", app)
        self.assertIn("/api/health/settings", app)
        self.assertNotIn('"Auto fix"', app)
        self.assertIn("Deterministic health checks are unavailable. Refresh to try again.", app)
        self.assertIn("/api/health/repair", app)
        self.assertNotIn("This may start repair tasks", app)
        self.assertNotIn("Automatic care", app)
        self.assertNotIn("watchdog", app.casefold())
        self.assertNotIn("watchdog", console.EDITABLE_SETTINGS)

    def test_visible_role_titles_are_normalized_by_icon_setting(self) -> None:
        _, enabled, _ = console.load_config(self.config)
        lead = console._role_from_title("LEAD - Console", enabled["labels"], enabled["role_icons"])
        self.assertEqual(lead["title"], "🧭LEAD - Console")
        duplicate = console._role_from_title("🧭🧭LEAD - Console", enabled["labels"], enabled["role_icons"])
        wrong = console._role_from_title("🔥CTRL - Ship console", enabled["labels"], enabled["role_icons"])
        repeated = console._role_from_title("🐙🐙CTRL - Ship console", enabled["labels"], enabled["role_icons"])
        developer = console._role_from_title("🔥DEV - Renderer", enabled["labels"], enabled["role_icons"])
        legacy_title = console._role_from_title("🐝MOTHER - Historical route", enabled["labels"], enabled["role_icons"], enabled["professions"])
        self.assertEqual(duplicate["title"], "🧭LEAD - Console")
        self.assertEqual(wrong["title"], "🐙CTRL - Ship console")
        self.assertEqual(repeated["title"], "🐙CTRL - Ship console")
        self.assertEqual(developer["title"], "💻DEV - Renderer")
        self.assertEqual((legacy_title["role"], legacy_title["title"]), ("doer", "📋MOTHER - Historical route"))
        console.update_config(self.config, {"role_icons.enabled": False})
        _, disabled, _ = console.load_config(self.config)
        ctrl = console._role_from_title("🐙CTRL - Ship console", disabled["labels"], disabled["role_icons"])
        self.assertEqual(ctrl["title"], "CTRL - Ship console")
        self.assertEqual(ctrl["icon"], "")

    def test_usage_saver_toggle_uses_validated_config_api(self) -> None:
        before = console.redacted_config_snapshot(self.config)
        self.assertFalse(before["settings"]["execution"]["usage_saver"])
        self.assertIn("execution.usage_saver", before["editable"])

        result = console.update_config(self.config, {"execution.usage_saver": True})
        self.assertTrue(result["settings"]["execution"]["usage_saver"])

    def test_config_projection_is_schema_derived_and_exposes_usage_saver(self) -> None:
        app = console.App(self.codex_home, self.config)
        projection = app.config_projection({"type": "global"})
        self.assertEqual(projection["contract_version"], console.CONFIG_CONTRACT_VERSION)
        self.assertEqual(projection["schema_version"], 4)
        self.assertRegex(projection["revision"], r"^[0-9a-f]{64}$")
        self.assertTrue(projection["text"])
        descriptors = {row["key"]: row for row in projection["descriptors"]}
        module = console.load_config_module()
        _, canonical_effective, _ = console.load_config(self.config)
        canonical_paths = {path for path, _ in console._config_leaf_items(canonical_effective)}
        self.assertEqual(set(descriptors), canonical_paths)
        self.assertTrue(all(row["classification"] in {"exposed", "internal", "unsupported"} for row in descriptors.values()))
        self.assertEqual(projection["editable"], sorted(
            path for path, row in descriptors.items() if row["classification"] == "exposed"
        ))

        usage_saver = descriptors["execution.usage_saver"]
        self.assertEqual(
            {
                usage_saver["section"], usage_saver["type"], usage_saver["default"],
                usage_saver["current"], usage_saver["advanced"], usage_saver["sensitivity"],
            },
            {"Essentials", "boolean", False, False, False, "normal"},
        )
        self.assertEqual(usage_saver["label"], "Usage saver · Experimental")
        self.assertIn("smart routing", usage_saver["help"])
        self.assertTrue(usage_saver["editable"])
        auto_fix = descriptors["monitoring.auto_health_enabled"]
        self.assertEqual(auto_fix["label"], "Automatic health review requests")
        self.assertEqual(auto_fix["help"], "Allow automatic health review requests. Repairs are not started.")
        self.assertEqual(auto_fix["default"], False)
        self.assertEqual(projection["health"]["auto_repair"]["key"], "monitoring.auto_health_enabled")
        private = descriptors["feedback.destination"]
        self.assertEqual(private["type"], "secret")
        self.assertEqual(private["classification"], "unsupported")
        self.assertFalse(private["editable"])
        self.assertNotIn("feedback.destination", projection["editable"])
        self.assertEqual(SERVER.read_bytes(), (console.PLUGIN_ROOT / "console" / "server.py").read_bytes())

    def test_config_source_global_write_is_revision_safe_replayed_and_fail_closed(self) -> None:
        app = console.App(self.codex_home, self.config)
        initial = app.config_projection({"type": "global"})
        changed_text = initial["text"].replace("fast_mode = false", "fast_mode = true", 1)
        payload = {
            "scope": {"type": "global"},
            "expected_revision": initial["revision"],
            "acknowledge": True,
            "text": changed_text,
            "operation_id": "config-global-1",
        }
        before = self.config.read_bytes()
        with self.assertRaisesRegex(console.ConsoleError, "acknowledge=true"):
            app.update_config_source({**payload, "acknowledge": False})
        self.assertEqual(self.config.read_bytes(), before)

        accepted = app.update_config_source(payload)
        self.assertTrue(accepted["settings"]["execution"]["fast_mode"])
        self.assertFalse(accepted["mutation_receipt"]["replayed"])
        self.assertEqual(accepted["mutation_receipt"]["changed_paths"], ["execution.fast_mode"])
        replayed = app.update_config_source(payload)
        self.assertTrue(replayed["mutation_receipt"]["replayed"])
        self.assertEqual(replayed["mutation_receipt"]["new_revision"], accepted["revision"])

        with self.assertRaises(console.ConsoleConflict):
            app.update_config_source({**payload, "operation_id": "config-global-stale"})
        current = app.config_projection({"type": "global"})
        current_bytes = self.config.read_bytes()
        for invalid_text, message in (
            (current["text"] + "\n[unknown]\nvalue = true\n", "unknown setting"),
            (current["text"].replace("[portfolio]\r\n", "[portfolio]\r\ntitle_prefix = \"legacy\"\r\n", 1), "deprecated config setting"),
            (current["text"].replace('mode = "BALANCED"', 'mode = "FAST"', 1), "deprecated config value"),
            ("[execution\n", "config TOML is invalid"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(console.ConsoleError, message):
                app.update_config_source({
                    "scope": {"type": "global"},
                    "expected_revision": current["revision"],
                    "acknowledge": True,
                    "text": invalid_text,
                    "operation_id": "config-invalid-" + message.replace(" ", "-"),
                })
            self.assertEqual(self.config.read_bytes(), current_bytes)
        atomic_projection = app.config_projection({"type": "global"})
        atomic_text = atomic_projection["text"].replace("open_on_start = true", "open_on_start = false", 1)
        self.assertNotEqual(atomic_text, atomic_projection["text"])
        with mock.patch.object(console.os, "replace", side_effect=OSError("replace blocked")):
            with self.assertRaisesRegex(console.ConsoleError, "replace blocked"):
                app.update_config_source({
                    "scope": {"type": "global"},
                    "expected_revision": atomic_projection["revision"],
                    "acknowledge": True,
                    "text": atomic_text,
                    "operation_id": "config-global-atomic-failure",
                })
        self.assertEqual(self.config.read_bytes(), current_bytes)
        self.assertIsNone(app.store.config_event("config-global-atomic-failure"))
        audit = app.store.config_event("config-global-1")
        self.assertIsNotNone(audit)
        self.assertNotIn("text", audit)
        self.assertNotIn("raw_config", audit)

        invalid_config = self.root / "invalid-editor" / "config.toml"
        invalid_config.parent.mkdir()
        invalid_config.write_bytes(
            b'"feedback"."destination" = "https://private.example/dotted"\n'
            b"[execution]\nfast_mode = \"yes\"\n"
        )
        invalid_app = console.App(self.codex_home, invalid_config)
        invalid_projection = invalid_app.config_projection({"type": "global"})
        self.assertEqual(invalid_projection["state"], "INVALID")
        self.assertFalse(invalid_projection["available"])
        self.assertEqual(invalid_projection["validation"]["status"], "INVALID")
        self.assertNotIn("private.example/dotted", invalid_projection["text"])
        self.assertEqual(len(invalid_projection["opaque_placeholders"]), 1)
        fast_descriptor = next(
            row for row in invalid_projection["descriptors"] if row["key"] == "execution.fast_mode"
        )
        self.assertIsNone(fast_descriptor["current"])
        self.assertEqual(fast_descriptor["value_state"], "UNKNOWN")

    def test_config_noop_snapshot_failure_retains_source_without_pending_recovery(self) -> None:
        app = console.App(self.codex_home, self.config)
        initial = app.config_projection({"type": "global"})
        before = self.config.read_bytes()
        with mock.patch.object(console.os, "replace", side_effect=OSError("replace blocked")):
            with self.assertRaisesRegex(console.ConsoleError, "replace blocked"):
                app.update_config_source({
                    "scope": initial["scope"],
                    "expected_revision": initial["revision"],
                    "acknowledge": True,
                    "text": initial["text"],
                    "operation_id": "config-noop-snapshot-failure",
                })
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(app.store.pending_config_events(), [])
        self.assertIsNone(app.store.config_event("config-noop-snapshot-failure"))
        self.assertEqual(app.config_projection(initial["scope"])["revision"], initial["revision"])

    def test_config_source_replay_retains_scope_and_cursor_across_restart(self) -> None:
        app = console.App(self.codex_home, self.config)
        global_initial = app.config_projection({"type": "global"})
        global_payload = {
            "scope": global_initial["scope"],
            "expected_revision": global_initial["revision"],
            "acknowledge": True,
            "text": global_initial["text"].replace("fast_mode = false", "fast_mode = true", 1),
            "operation_id": "config-replay-scope-global",
        }
        global_fresh = app.update_config_source(global_payload)
        applied_bytes = self.config.read_bytes()

        restarted = console.App(self.codex_home, self.config)
        global_replay = restarted.update_config_source(global_payload)
        self.assertTrue(global_replay["mutation_receipt"]["replayed"])
        self.assertEqual(self.config.read_bytes(), applied_bytes)
        for key in (
            "accepted",
            "action",
            "operation_id",
            "scope",
            "expected_revision",
            "new_revision",
            "changed_paths",
            "acknowledged",
            "audit_event",
            "source_kind",
        ):
            self.assertEqual(
                global_replay["mutation_receipt"][key],
                global_fresh["mutation_receipt"][key],
            )

        project_initial = restarted.config_projection({"type": "project", "project_id": "project:alpha"})
        project_payload = {
            "scope": project_initial["scope"],
            "expected_revision": project_initial["revision"],
            "acknowledge": True,
            "text": "[execution]\nfast_mode = true\n",
            "operation_id": "config-replay-scope-project",
        }
        project_fresh = restarted.update_config_source(project_payload)
        retained = copy.deepcopy(restarted.store.config_event(project_payload["operation_id"]))

        replay_app = console.App(self.codex_home, self.config)
        project_replay = replay_app.update_config_source(project_payload)
        self.assertTrue(project_replay["mutation_receipt"]["replayed"])
        self.assertEqual(
            project_replay["mutation_receipt"]["scope"]["accepted_cursor"],
            project_initial["scope"]["accepted_cursor"],
        )
        for key in (
            "accepted",
            "action",
            "operation_id",
            "scope",
            "expected_revision",
            "new_revision",
            "changed_paths",
            "acknowledged",
            "audit_event",
            "source_kind",
        ):
            self.assertEqual(
                project_replay["mutation_receipt"][key],
                project_fresh["mutation_receipt"][key],
            )

        with self.assertRaises(console.ConsoleConflict):
            replay_app.update_config_source({
                **project_payload,
                "scope": global_replay["scope"],
                "expected_revision": global_replay["revision"],
                "text": global_replay["text"],
            })
        with self.assertRaises(console.ConsoleConflict):
            replay_app.update_config_source({
                **project_payload,
                "scope": {
                    **project_payload["scope"],
                    "accepted_cursor": {"type": "codex_project_roster_v1", "digest": "0" * 64},
                },
            })
        self.assertEqual(replay_app.store.config_event(project_payload["operation_id"]), retained)
        self.assertEqual(
            replay_app.config_projection(project_initial["scope"])["revision"],
            project_fresh["revision"],
        )
        self.assertEqual(self.config.read_bytes(), applied_bytes)

    def test_global_config_audit_failure_rolls_back_bytes_and_revision(self) -> None:
        app = console.App(self.codex_home, self.config)
        initial = app.config_projection({"type": "global"})
        changed_text = initial["text"].replace("fast_mode = false", "fast_mode = true", 1)
        before = self.config.read_bytes()
        with mock.patch.object(
            app.store,
            "retain_config_event",
            side_effect=console.ConsoleError("audit append blocked"),
        ):
            with self.assertRaisesRegex(console.ConsoleError, "audit append blocked"):
                app.update_config_source({
                    "scope": {"type": "global"},
                    "expected_revision": initial["revision"],
                    "acknowledge": True,
                    "text": changed_text,
                    "operation_id": "config-audit-failure",
                })
        self.assertEqual(self.config.read_bytes(), before)
        restored = app.config_projection({"type": "global"})
        self.assertEqual(restored["revision"], initial["revision"])
        self.assertIsNone(app.store.config_event("config-audit-failure"))
        self.assertEqual(app.store.pending_config_events(), [])

        accepted = app.update_config_source({
            "scope": {"type": "global"},
            "expected_revision": initial["revision"],
            "acknowledge": True,
            "text": changed_text,
            "operation_id": "config-audit-retry",
        })
        replayed = app.update_config_source({
            "scope": {"type": "global"},
            "expected_revision": initial["revision"],
            "acknowledge": True,
            "text": changed_text,
            "operation_id": "config-audit-retry",
        })
        self.assertFalse(accepted["mutation_receipt"]["replayed"])
        self.assertTrue(replayed["mutation_receipt"]["replayed"])
        self.assertEqual(replayed["revision"], accepted["revision"])

    def test_pending_global_config_transaction_recovers_on_restart(self) -> None:
        app = console.App(self.codex_home, self.config)
        initial = app.config_projection({"type": "global"})
        changed_text = initial["text"].replace("fast_mode = false", "fast_mode = true", 1)
        before = self.config.read_bytes()
        with (
            mock.patch.object(
                app.store,
                "retain_config_event",
                side_effect=console.ConsoleError("audit append blocked"),
            ),
            mock.patch.object(
                app.store,
                "abort_config_event",
                side_effect=console.ConsoleError("abort blocked"),
            ),
        ):
            with self.assertRaisesRegex(console.ConsoleError, "recovery could not be proven"):
                app.update_config_source({
                    "scope": {"type": "global"},
                    "expected_revision": initial["revision"],
                    "acknowledge": True,
                    "text": changed_text,
                    "operation_id": "config-restart-recovery",
                })
        self.assertEqual(self.config.read_bytes(), before)
        restarted = console.App(self.codex_home, self.config)
        self.assertEqual(restarted.config_projection({"type": "global"})["revision"], initial["revision"])
        self.assertEqual(restarted.store.pending_config_events(), [])
        self.assertIsNone(restarted.store.config_event("config-restart-recovery"))
        self.assertFalse(any(self.config.parent.glob(f".{self.config.name}.swarm-console-rollback-*")))

    def test_settings_restore_requires_revision_ack_operation_and_keeps_scopes_explicit(self) -> None:
        app = console.App(self.codex_home, self.config)

        handler = self._handler("127.0.0.1", "127.0.0.1:4788", token=app.token)
        handler.server = SimpleNamespace(app=app)
        handler.path = "/api/settings/restore"
        handler._payload = mock.Mock(return_value={})
        handler._json = mock.Mock()
        handler._error = mock.Mock()
        handler.do_POST()
        handler._error.assert_called_once_with(
            console.HTTPStatus.BAD_REQUEST,
            "settings restore requires exact scope, expected_revision, acknowledge, and operation_id fields",
        )

        with self.assertRaisesRegex(console.ConsoleError, "acknowledge=true"):
            app.restore_settings({
                "scope": {"type": "global"},
                "expected_revision": "0" * 64,
                "acknowledge": False,
                "operation_id": "restore-no-ack",
            })

        global_projection = app.config_projection({"type": "global"})
        app.update_config_source({
            "scope": global_projection["scope"],
            "expected_revision": global_projection["revision"],
            "acknowledge": True,
            "text": global_projection["text"].replace("heartbeat_minutes = 30", "heartbeat_minutes = 45", 1),
            "operation_id": "restore-prepare-global",
        })
        project_projection = app.config_projection({"type": "project", "project_id": "project:alpha"})
        project_updated = app.update_config_source({
            "scope": project_projection["scope"],
            "expected_revision": project_projection["revision"],
            "acknowledge": True,
            "text": "[execution]\nfast_mode = true\n",
            "operation_id": "restore-prepare-project",
        })
        ctrl_projection = app.ctrl_settings("root")
        ctrl_updated = app.update_ctrl_settings(
            "root", {"reasoning": "high"}, ctrl_projection["revision"],
        )

        restored_global = app.restore_settings({
            "scope": {"type": "global"},
            "expected_revision": app.config_projection({"type": "global"})["revision"],
            "acknowledge": True,
            "operation_id": "restore-global",
        })
        self.assertEqual(restored_global["settings"]["monitoring"]["heartbeat_minutes"], 30)
        self.assertEqual(app.store.config_event("restore-global")["action"], "global_config_reset")
        self.assertNotIn("text", app.store.config_event("restore-global"))

        after_global = app.config_projection(project_updated["scope"])
        self.assertEqual(after_global["overridden_paths"], ["execution.fast_mode"])
        self.assertTrue(after_global["settings"]["execution"]["fast_mode"])
        self.assertTrue(after_global["global_settings"]["monitoring"]["heartbeat_minutes"] == 30)
        self.assertTrue(app.ctrl_settings("root")["customized"])

        restored_project = app.restore_settings({
            "scope": after_global["scope"],
            "expected_revision": after_global["revision"],
            "acknowledge": True,
            "operation_id": "restore-project",
        })
        self.assertEqual(restored_project["overridden_paths"], [])
        self.assertEqual(app.store.config_event("restore-project")["action"], "project_config_reset")

        restored_ctrl = app.restore_settings({
            "scope": {"type": "ctrl", "ctrl_id": "root"},
            "expected_revision": ctrl_updated["revision"],
            "acknowledge": True,
            "operation_id": "restore-ctrl",
        })
        self.assertFalse(restored_ctrl["customized"])
        self.assertEqual(app.store.config_event("restore-ctrl")["action"], "ctrl_settings_reset")
        self.assertEqual(restored_ctrl["mutation_receipt"]["audit_event"], console.CONFIG_EVENT_KIND)
        self.assertEqual(app.config_projection({"type": "global"})["reset_contract"]["ctrl"]["endpoint"], "/api/ctrl-settings/reset")

    def test_config_editor_opaque_private_round_trip_preserves_source_bytes(self) -> None:
        private_bytes = self.config.read_bytes().replace(
            b'destination = ""\r\n',
            b'  destination\t=\t"https://private.example/a#token"  # retain this\r\n',
            1,
        )
        self.config.write_bytes(private_bytes)
        app = console.App(self.codex_home, self.config)
        projection = app.config_projection({"type": "global"})
        self.assertEqual(len(projection["opaque_placeholders"]), 1)
        token = projection["opaque_placeholders"][0]["token"]
        self.assertNotIn("private.example", projection["text"])
        self.assertIn("destination\t=\t", projection["text"])
        self.assertIn("# retain this", projection["text"])

        accepted = app.update_config_source({
            "scope": {"type": "global"},
            "expected_revision": projection["revision"],
            "acknowledge": True,
            "text": projection["text"],
            "operation_id": "config-private-round-trip",
        })
        self.assertEqual(self.config.read_bytes(), private_bytes)
        self.assertNotIn("private.example", json.dumps(accepted, ensure_ascii=False))
        self.assertNotIn("private.example", json.dumps(app.store.config_event("config-private-round-trip")))

        tampered = projection["text"].replace(
            json.dumps(token), '"https://replacement.example/secret"', 1,
        )
        with self.assertRaisesRegex(console.ConsoleError, "must retain its current opaque placeholder"):
            app.update_config_source({
                "scope": {"type": "global"},
                "expected_revision": accepted["revision"],
                "acknowledge": True,
                "text": tampered,
                "operation_id": "config-private-replaced",
            })
        self.assertEqual(self.config.read_bytes(), private_bytes)

    def test_project_config_overlay_inherits_overrides_resets_and_binds_cursor(self) -> None:
        app = console.App(self.codex_home, self.config)
        initial = app.config_projection({"type": "project", "project_id": "project:alpha"})
        self.assertEqual(initial["text"], "")
        self.assertEqual(initial["overridden_paths"], [])
        self.assertEqual(initial["project"]["root"], "C:/work/alpha")
        self.assertIn("inherits global values", initial["inheritance"]["warning"])
        global_before = self.config.read_bytes()
        overlay_text = "[execution]\nfast_mode = true\n"
        updated = app.update_config_source({
            "scope": initial["scope"],
            "expected_revision": initial["revision"],
            "acknowledge": True,
            "text": overlay_text,
            "operation_id": "config-project-1",
        })
        self.assertTrue(updated["settings"]["execution"]["fast_mode"])
        self.assertFalse(updated["global_settings"]["execution"]["fast_mode"])
        self.assertEqual(updated["overridden_paths"], ["execution.fast_mode"])
        self.assertIn("stop following global changes", updated["inheritance"]["warning"])
        self.assertEqual(self.config.read_bytes(), global_before)
        skill_overlay = app.store.skill_scope("project", "project:alpha")
        self.assertEqual(skill_overlay["revision"], 0)
        self.assertEqual(skill_overlay["profile"], "default")
        self.assertEqual(skill_overlay["preferred_ids"], [])

        global_projection = app.config_projection({"type": "global"})
        global_updated = app.update_config_source({
            "scope": {"type": "global"},
            "expected_revision": global_projection["revision"],
            "acknowledge": True,
            "text": global_projection["text"].replace("usage_saver = false", "usage_saver = true", 1),
            "operation_id": "config-global-inheritance",
        })
        global_after = self.config.read_bytes()
        project_after_global = app.config_projection(updated["scope"])
        self.assertTrue(project_after_global["settings"]["execution"]["fast_mode"])
        self.assertTrue(project_after_global["settings"]["execution"]["usage_saver"])
        self.assertTrue(global_updated["settings"]["execution"]["usage_saver"])

        with self.assertRaises(console.ConsoleConflict):
            app.update_config_source({
                "scope": {
                    **updated["scope"],
                    "accepted_cursor": {"type": "codex_project_roster_v1", "digest": "0" * 64},
                },
                "expected_revision": updated["revision"],
                "acknowledge": True,
                "text": "[execution]\nfast_mode = false\n",
                "operation_id": "config-project-wrong-cursor",
            })

        reset = app.reset_config_source({
            "scope": project_after_global["scope"],
            "expected_revision": project_after_global["revision"],
            "acknowledge": True,
            "operation_id": "config-project-reset",
        })
        self.assertFalse(reset["settings"]["execution"]["fast_mode"])
        self.assertEqual(reset["overridden_paths"], [])
        self.assertEqual(reset["text"], "")
        self.assertFalse(reset["mutation_receipt"]["replayed"])
        self.assertEqual(self.config.read_bytes(), global_after)

        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "INSERT INTO project_roots VALUES (?,?,?)",
                ("project:alpha", 1, "C:/work/other-alpha"),
            )
            connection.commit()
        with self.assertRaisesRegex(console.ConsoleError, "one unambiguous canonical project root"):
            app.config_projection({"type": "project", "project_id": "project:alpha"})

    def test_chat_relay_toggle_uses_only_the_canonical_validated_config_path(self) -> None:
        before = console.redacted_config_snapshot(self.config)
        self.assertFalse(before["settings"]["chat_relay"]["enabled"])
        self.assertIn("chat_relay.enabled", before["editable"])
        expected = copy.deepcopy(before["settings"])
        expected["chat_relay"]["enabled"] = True

        with (
            mock.patch.object(console.subprocess, "Popen", side_effect=AssertionError("relay process invoked")),
            mock.patch.object(console, "CodexAppServerAdapter", side_effect=AssertionError("relay adapter invoked")),
        ):
            enabled = console.update_config(self.config, {"chat_relay.enabled": True})
            observed = console.redacted_config_snapshot(self.config)

        self.assertEqual(enabled["settings"], expected)
        self.assertEqual(observed["settings"], expected)
        self.assertEqual(enabled["mutation_receipt"]["changed_keys"], ["chat_relay.enabled"])
        self.assertTrue(self.config.with_suffix(".toml.swarm-console.bak").exists())

        disabled = console.update_config(self.config, {"chat_relay.enabled": False})
        self.assertFalse(disabled["settings"]["chat_relay"]["enabled"])
        before_invalid = self.config.read_bytes()
        with self.assertRaisesRegex(console.ConsoleError, "chat_relay.enabled must be a boolean"):
            console.update_config(self.config, {"chat_relay.enabled": "yes"})
        self.assertEqual(self.config.read_bytes(), before_invalid)

    def test_chat_relay_missing_and_invalid_config_reads_fail_without_repair(self) -> None:
        missing = self.root / "missing" / "config.toml"
        snapshot = console.redacted_config_snapshot(missing)
        self.assertFalse(snapshot["exists"])
        self.assertFalse(snapshot["settings"]["chat_relay"]["enabled"])
        self.assertFalse(missing.exists())

        invalid = self.root / "invalid" / "config.toml"
        invalid.parent.mkdir()
        invalid.write_text("[chat_relay]\nenabled = \"yes\"\n", encoding="utf-8")
        retained = invalid.read_bytes()
        with self.assertRaisesRegex(console.ConsoleError, "chat_relay.enabled must be true or false"):
            console.redacted_config_snapshot(invalid)
        with self.assertRaisesRegex(console.ConsoleError, "chat_relay.enabled must be true or false"):
            console.update_config(invalid, {"chat_relay.enabled": True})
        self.assertEqual(invalid.read_bytes(), retained)

    def test_config_post_requires_revision_acknowledgement_and_operation_identity(self) -> None:
        def config_handler(
            peer: str = "127.0.0.1",
            *,
            origin: str = "",
            token: str | None = None,
            payload: object = None,
        ):
            app = console.App(self.codex_home, self.config)
            handler = self._handler(peer, "localhost:4788", origin=origin, token=token)
            handler.server.app = app
            handler.headers["X-Swarm-Token"] = app.token if token is None else token
            handler.path = "/api/config"
            handler._payload = mock.Mock(
                return_value={"changes": {"chat_relay.enabled": True}} if payload is None else payload,
            )
            handler._json = mock.Mock()
            handler._error = mock.Mock()
            return handler, app

        with mock.patch.object(console, "update_config") as legacy_update:
            for handler, _ in (
                config_handler("192.0.2.44"),
                config_handler(origin="http://evil.example"),
                config_handler(token="wrong"),
            ):
                handler.do_POST()
                handler._error.assert_called_once()
            legacy_update.assert_not_called()

        malformed, _ = config_handler(payload=[])
        with mock.patch.object(console, "update_config") as legacy_update:
            malformed.do_POST()
            legacy_update.assert_not_called()
        malformed._error.assert_called_once_with(
            console.HTTPStatus.BAD_REQUEST,
            "config update requires exact scope, expected_revision, acknowledge, text, and operation_id fields",
        )

        app = console.App(self.codex_home, self.config)
        projection = app.config_projection({"type": "global"})
        authorized, _ = config_handler(
            payload={
                "scope": {"type": "global"},
                "expected_revision": projection["revision"],
                "acknowledge": True,
                "text": projection["text"].replace("fast_mode = false", "fast_mode = true", 1),
                "operation_id": "config-http-1",
            },
        )
        authorized.server.app = app
        authorized.headers.replace_header("X-Swarm-Token", app.token)
        with mock.patch.object(console, "update_config") as legacy_update:
            authorized.do_POST()
            legacy_update.assert_not_called()
        authorized._json.assert_called_once()

    def test_fast_mode_is_the_only_persisted_fast_control(self) -> None:
        before = console.redacted_config_snapshot(self.config)
        self.assertFalse(before["settings"]["execution"]["fast_mode"])
        self.assertIn("execution.fast_mode", before["editable"])
        self.assertNotIn("execution.service_tier", before["editable"])
        self.assertNotIn("service_tier", before["settings"]["execution"])

        result = console.update_config(self.config, {"execution.fast_mode": True})
        self.assertTrue(result["settings"]["execution"]["fast_mode"])
        self.assertNotIn("service_tier", result["settings"]["execution"])
        result = console.update_config(self.config, {"execution.fast_mode": False})
        self.assertFalse(result["settings"]["execution"]["fast_mode"])
        with self.assertRaisesRegex(console.ConsoleError, "must be a boolean"):
            console.update_config(self.config, {"execution.fast_mode": "yes"})

    def test_fast_mode_atomic_update_failure_preserves_original(self) -> None:
        before = self.config.read_bytes()
        with mock.patch.object(console.os, "replace", side_effect=OSError("replace blocked")):
            with self.assertRaisesRegex(console.ConsoleError, "replace blocked"):
                console.update_config(self.config, {"execution.fast_mode": True})
        self.assertEqual(self.config.read_bytes(), before)

    def test_console_write_migrates_legacy_fast_alias_without_losing_effective_choice(self) -> None:
        text = self.config.read_text(encoding="utf-8")
        text = text.replace("fast_mode = false", 'service_tier = "fast"')
        self.config.write_text(text, encoding="utf-8")
        before = console.redacted_config_snapshot(self.config)
        self.assertTrue(before["settings"]["execution"]["fast_mode"])

        result = console.update_config(self.config, {"console.open_on_start": False})
        persisted = self.config.read_text(encoding="utf-8")
        self.assertTrue(result["settings"]["execution"]["fast_mode"])
        self.assertNotIn("service_tier", persisted)
        self.assertIn("fast_mode = true", persisted)

    def test_per_ctrl_settings_cannot_create_a_second_fast_control(self) -> None:
        self.assertEqual(set(console.CTRL_OVERRIDE_FIELDS), {"model", "reasoning"})
        app = (console.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("ctrl-service-tier", app)
        self.assertNotIn("execution.service_tier", app)
        projection = console.App(self.codex_home, self.config).config_projection({"type": "global"})
        self.assertEqual([row["key"] for row in projection["descriptors"]].count("execution.fast_mode"), 1)
        self.assertNotIn("settingToggle('execution.fast_mode'", app)
        self.assertEqual(app.count("settingsSpeedMarkup()"), 1)

    def test_stale_console_cache_fails_with_a_concise_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            advisory = console.static_bundle_advisory(root)
            self.assertIn("cache is stale or incomplete", advisory)
            self.assertNotIn("index.html", advisory)
            self.assertNotIn(str(root), advisory)
            for filename, _ in set(console.STATIC_FILES.values()):
                (root / filename).write_text("fixture", encoding="utf-8")
            self.assertIsNone(console.static_bundle_advisory(root))

    def test_spark_small_work_lane_is_off_by_default_and_configurable(self) -> None:
        before = console.redacted_config_snapshot(self.config)
        self.assertFalse(before["settings"]["boost"]["spark_enabled"])
        self.assertEqual(before["settings"]["boost"]["spark_reasoning"], "xhigh")
        self.assertIn("boost.spark_enabled", before["editable"])
        self.assertIn("boost.spark_reasoning", before["editable"])
        result = console.update_config(
            self.config,
            {"boost.spark_enabled": True, "boost.spark_reasoning": "medium"},
        )
        self.assertTrue(result["settings"]["boost"]["spark_enabled"])
        self.assertEqual(result["settings"]["boost"]["spark_reasoning"], "medium")

    def test_hq_start_and_browser_open_are_separate_default_on_settings(self) -> None:
        before = console.redacted_config_snapshot(self.config)
        self.assertTrue(before["settings"]["console"]["auto_start"])
        self.assertTrue(before["settings"]["console"]["open_on_start"])
        self.assertIn("console.auto_start", before["editable"])
        self.assertIn("console.open_on_start", before["editable"])
        result = console.update_config(
            self.config,
            {"console.auto_start": False, "console.open_on_start": False},
        )
        self.assertFalse(result["settings"]["console"]["auto_start"])
        self.assertFalse(result["settings"]["console"]["open_on_start"])

    def test_usage_saver_rejects_non_boolean_without_writing(self) -> None:
        before = self.config.read_bytes()
        with self.assertRaisesRegex(console.ConsoleError, "must be a boolean"):
            console.update_config(self.config, {"execution.usage_saver": "yes"})
        self.assertEqual(self.config.read_bytes(), before)

    def test_spark_remains_configurable_without_a_duplicate_essentials_toggle(self) -> None:
        index = (console.STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        app = (console.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertNotIn('id="usage-saver-toggle"', index)
        self.assertNotIn("settingToggle('boost.spark_enabled'", app)
        self.assertIn("boost.spark_enabled", console.redacted_config_snapshot(self.config)["editable"])
        self.assertNotIn("No browser, web lookup, ImageGen", app)
        self.assertNotIn("saveUsageSaver", app)
        self.assertNotIn("save-spark", app)
        self.assertNotIn("spark-model", app)

    def test_console_ui_fixture_is_structurally_valid(self) -> None:
        fixture_path = Path(__file__).parent / "fixtures" / "console-ui.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(set(fixture), {"bootstrap", "config", "overview", "proofFeed", "usageHistory", "projectProgressFeed", "diagnostics", "diagnosticHistory", "healthSettings", "storage", "ctrlSettings"})
        progress_feed = fixture["projectProgressFeed"]
        self.assertEqual(set(progress_feed), {"ok", "enabled", "limit", "project_id", "cursor", "items"})
        self.assertTrue(progress_feed["ok"])
        self.assertTrue(progress_feed["enabled"])
        self.assertEqual(progress_feed["limit"], 4)
        self.assertEqual(progress_feed["project_id"], "project:fixture")
        self.assertEqual(set(progress_feed["cursor"]), {"event_seq", "event_id", "event_digest"})
        self.assertEqual(len(progress_feed["items"]), 2)
        for item in progress_feed["items"]:
            self.assertEqual(set(item), {"event_id", "event_digest", "event_seq", "project_id", "task_id", "owner_id", "material_update_sentence", "observed_at_ms", "flags"})
            self.assertEqual(item["project_id"], "project:fixture")
            self.assertTrue(item["material_update_sentence"])
        self.assertFalse(fixture["config"]["settings"]["execution"]["usage_saver"])
        self.assertIn("execution.usage_saver", fixture["config"]["editable"])
        self.assertFalse(fixture["config"]["settings"]["execution"]["fast_mode"])
        self.assertIn("execution.fast_mode", fixture["config"]["editable"])
        self.assertNotIn("execution.service_tier", fixture["config"]["editable"])
        self.assertNotIn("service_tier", fixture["config"]["settings"]["execution"])
        self.assertTrue(fixture["config"]["settings"]["console"]["open_on_start"])
        self.assertIn("console.open_on_start", fixture["config"]["editable"])
        self.assertTrue(fixture["config"]["settings"]["console"]["project_progress_feed_enabled"])
        self.assertEqual(fixture["config"]["settings"]["console"]["project_progress_feed_lines"], 4)
        self.assertIn("console.project_progress_feed_enabled", fixture["config"]["editable"])
        self.assertIn("console.project_progress_feed_lines", fixture["config"]["editable"])
        self.assertEqual(fixture["config"]["settings"]["automation"]["mode"], "standard")
        self.assertIn("automation.mode", fixture["config"]["editable"])
        self.assertNotIn("archive_completed_tasks", fixture["config"]["settings"]["lifecycle"])
        self.assertIn("boost.spark_enabled", fixture["config"]["editable"])
        self.assertEqual(fixture["config"]["settings"]["boost"]["spark_reasoning"], "xhigh")

    def test_hierarchy_omits_explanatory_metadata_surfaces(self) -> None:
        index = (console.STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("stage-legend", index)
        self.assertNotIn("claim-note", index)
        self.assertNotIn("Recent means", index)

    def test_invalid_config_update_preserves_source(self) -> None:
        before = self.config.read_bytes()
        with self.assertRaises(console.ConsoleError):
            console.update_config(self.config, {"portfolio.max_active_tasks": 0})
        self.assertEqual(self.config.read_bytes(), before)

    def test_non_editable_setting_is_rejected(self) -> None:
        with self.assertRaises(console.ConsoleError):
            console.update_config(self.config, {"feedback.destination": "https://example.invalid"})

    def test_recovery_attempt_count_is_a_fixed_invariant_not_a_console_control(self) -> None:
        self.assertNotIn("recovery.max_attempts", console.EDITABLE_SETTINGS)
        app = (console.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertNotIn('"recovery.max_attempts"', app)
        with self.assertRaises(console.ConsoleError):
            console.update_config(self.config, {"recovery.max_attempts": 0})


if __name__ == "__main__":
    unittest.main()
