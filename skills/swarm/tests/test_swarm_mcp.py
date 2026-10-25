from __future__ import annotations

import json
import hashlib
import io
import importlib.util
from unittest.mock import patch, Mock
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "scripts" / "swarm_mcp.py"


spec = importlib.util.spec_from_file_location("swarm_mcp", SERVER)
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)


def call(process: subprocess.Popen[str], request: dict) -> dict:
    assert process.stdin and process.stdout
    process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()
    return json.loads(process.stdout.readline())


class SwarmMCPTests(unittest.TestCase):
    def test_model_ticket_discovery_and_wire_commands_keep_existing_authority(self):
        sys.path.insert(0, str(mcp.REPO_ROOT))
        from console.server import App
        from console.tests.test_console import SwarmConsoleTests
        from console.tests.test_project_model_views import project_fixture, markdown_fixture
        fixture = SwarmConsoleTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        brief = fixture.alpha_root / "SWARM.md"
        brief.write_text(markdown_fixture(project_fixture("alpha")), encoding="utf-8")
        transport = Mock()
        app = App(fixture.codex_home, fixture.config, auto_bridge=transport)

        def wire(method, params):
            request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            with patch.object(mcp.SwarmProjection, "_load_app", return_value=app), \
                 patch.object(sys, "stdin", io.StringIO(json.dumps(request))), \
                 patch.object(sys, "stdout", new_callable=io.StringIO) as output:
                self.assertEqual(mcp.serve(telemetry_path=fixture.root / "ticket-wire.jsonl"), 0)
            return json.loads(output.getvalue())["result"]

        def ticket(arguments):
            return wire("tools/call", {"name": "swarm_project_tickets", "arguments": arguments})

        tools = wire("tools/list", {})["tools"]
        spec = next(t for t in tools if t["name"] == "swarm_project_tickets")
        self.assertEqual(spec["_meta"]["ui"]["visibility"], ["model", "app"])
        self.assertEqual(sum(t["name"] == spec["name"] for t in tools), 1)
        self.assertEqual(spec["inputSchema"]["properties"]["operation"]["enum"], ["read", "create", "update"])
        for tool in tools:
            if tool["name"] in {"swarm_library_read", "swarm_flow_save", "swarm_flow_assign",
                                "swarm_settings_read", "swarm_settings_save"}:
                self.assertEqual(tool["_meta"]["ui"]["visibility"], ["app"])
        read = {"operation": "read", "project_id": "project:alpha"}
        initial = ticket(read)
        self.assertFalse(initial["isError"])
        create = {**read, "operation": "create", "expected_digest": initial["structuredContent"]["source_digest"],
                  "acknowledge": True, "collection": "goals", "record_id": "model-ticket",
                  "changes": {"label": "Wire goal"}, "project_code": "TEST"}
        before = brief.read_bytes()
        for change in ({"acknowledge": False}, {"acknowledge": 1}, {"path": "elsewhere"},
                       {"project_id": "foreign-project"}, {"operation": "execute"}):
            self.assertTrue(ticket({**create, **change})["isError"], change)
            self.assertEqual(brief.read_bytes(), before)
            self.assertFalse(app.progress_ledger._state.path.exists())
        saved = ticket(create)
        self.assertFalse(saved["isError"])
        record = next(r for r in saved["structuredContent"]["records"] if r["id"] == "model-ticket")
        self.assertEqual(record["display_id"], "TEST-1")
        source_bytes, ledger_bytes = brief.read_bytes(), app.progress_ledger._state.path.read_bytes()
        app = App(fixture.codex_home, fixture.config, auto_bridge=transport)
        self.assertTrue(ticket(create)["structuredContent"]["replayed"])
        self.assertEqual(brief.read_bytes(), source_bytes)
        self.assertEqual(app.progress_ledger._state.path.read_bytes(), ledger_bytes)
        # The existing command admits project_code only on create. An update carrying it fails the
        # exact-field check before any digest comparison: REJECTED, not CONFLICT, and no write.
        update = {key: value for key, value in create.items() if key != "project_code"}
        update.update(operation="update", changes={"label": "Updated wire goal"})
        malformed = ticket({**update, "project_code": "TEST"})
        self.assertTrue(malformed["isError"])
        self.assertEqual(malformed["structuredContent"]["state"], "REJECTED")
        self.assertEqual(brief.read_bytes(), source_bytes)
        self.assertEqual(app.progress_ledger._state.path.read_bytes(), ledger_bytes)
        # A well-formed update whose expected_digest predates the create is a stale CAS: CONFLICT, no write.
        rejected = ticket(update)
        self.assertTrue(rejected["isError"])
        self.assertEqual(rejected["structuredContent"]["state"], "CONFLICT")
        self.assertEqual(rejected["structuredContent"]["code"], "SOURCE_CONFLICT")
        self.assertEqual(brief.read_bytes(), source_bytes)
        self.assertEqual(app.progress_ledger._state.path.read_bytes(), ledger_bytes)
        update["expected_digest"] = saved["structuredContent"]["source_digest"]
        edited = ticket(update)
        self.assertFalse(edited["isError"])
        app = App(fixture.codex_home, fixture.config, auto_bridge=transport)
        row = next(r for r in ticket(read)["structuredContent"]["records"] if r["id"] == "model-ticket")
        self.assertEqual((row["label"], row["display_id"]), ("Updated wire goal", "TEST-1"))
        # A saved host root does not authorize a brief naming another project.
        brief.write_text(markdown_fixture(project_fixture("foreign")), encoding="utf-8")
        foreign = brief.read_bytes()
        self.assertTrue(ticket(read)["isError"])
        self.assertTrue(ticket({**update, "expected_digest": edited["structuredContent"]["source_digest"]})["isError"])
        self.assertEqual(brief.read_bytes(), foreign)
        self.assertEqual(app.progress_ledger._state.path.read_bytes(), ledger_bytes)
        self.assertEqual(transport.mock_calls, [])

    def test_ticket_write_uncertainty_is_typed_and_reserved_identity_survives_restart(self):
        sys.path.insert(0, str(mcp.REPO_ROOT))
        from console import server
        from console.tests.test_console import SwarmConsoleTests
        from console.tests.test_project_model_views import project_fixture, markdown_fixture
        fixture = SwarmConsoleTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        brief = fixture.alpha_root / "SWARM.md"
        brief.write_text(markdown_fixture(project_fixture("alpha")), encoding="utf-8")
        transport = Mock()
        projection = mcp.SwarmProjection()
        projection._app = server.App(fixture.codex_home, fixture.config, auto_bridge=transport)
        read = {"operation": "read", "project_id": "project:alpha"}
        request = {**read, "operation": "create", "acknowledge": True, "collection": "goals",
                   "record_id": "reserved-first", "changes": {"label": "Proof goal"}, "project_code": "TEST",
                   "expected_digest": projection.call("swarm_project_tickets", read)["source_digest"]}
        before = brief.read_bytes()
        module = sys.modules[server.mutate_project_tickets.__module__]
        with patch.object(module, "_replace_brief_bytes", side_effect=OSError("private/path/SWARM.md")):
            result = projection.call("swarm_project_tickets", request)
        self.assertEqual((result["ok"], result["state"], result["code"]),
                         (False, "REJECTED", "SOURCE_WRITE_UNCERTAIN"))
        self.assertNotIn("private", json.dumps(result))
        self.assertEqual(brief.read_bytes(), before)
        ledger_path = projection._app.progress_ledger._state.path
        reserved = ledger_path.read_bytes()
        projection._app = server.App(fixture.codex_home, fixture.config, auto_bridge=transport)
        saved = projection.call("swarm_project_tickets", request)
        self.assertEqual(next(r for r in saved["records"] if r["id"] == "reserved-first")["display_id"], "TEST-1")
        self.assertEqual(sum(r["id"] == "reserved-first" for r in saved["records"]), 1)
        self.assertEqual(ledger_path.read_bytes(), reserved)
        second = {**request, "record_id": "reserved-second", "expected_digest": saved["source_digest"]}
        with patch.object(module, "_replace_brief_bytes", side_effect=OSError("private/path")):
            self.assertEqual(projection.call("swarm_project_tickets", second)["code"], "SOURCE_WRITE_UNCERTAIN")
        reserved = ledger_path.read_bytes()
        edited = projection.call("swarm_project_tickets", {**read, "operation": "update", "acknowledge": True,
            "collection": "goals", "record_id": "reserved-first", "expected_digest": saved["source_digest"],
            "changes": {"label": "Another author's edit"}})
        source = brief.read_bytes()
        projection._app = server.App(fixture.codex_home, fixture.config, auto_bridge=transport)
        retry = {**second, "expected_digest": edited["source_digest"]}
        self.assertEqual(projection.call("swarm_project_tickets", retry)["code"], "RECORD_ID_RESERVED")
        self.assertEqual(brief.read_bytes(), source)
        self.assertEqual(ledger_path.read_bytes(), reserved)
        fresh = projection.call("swarm_project_tickets", {**retry, "record_id": "fresh-third"})
        self.assertEqual(next(r for r in fresh["records"] if r["id"] == "fresh-third")["display_id"], "TEST-3")
        self.assertEqual(transport.mock_calls, [])

    def test_ticket_tool_real_app_prefix_retry_reload_and_no_dispatch(self):
        sys.path.insert(0, str(mcp.REPO_ROOT))
        from console.server import App
        from console.tests.test_console import SwarmConsoleTests
        from console.tests.test_project_model_views import project_fixture, markdown_fixture
        fixture = SwarmConsoleTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        brief = fixture.alpha_root / "SWARM.md"
        brief.write_text(markdown_fixture(project_fixture("alpha")), encoding="utf-8")
        transport = Mock()
        projection = mcp.SwarmProjection()
        projection._app = App(fixture.codex_home, fixture.config, auto_bridge=transport)
        read = {"operation": "read", "project_id": "project:alpha"}
        initial = projection.call("swarm_project_tickets", read)
        request = {**read, "operation": "create", "expected_digest": initial["source_digest"],
                   "acknowledge": True, "collection": "goals", "record_id": "proof-ticket", "changes": {"label": "Proof goal"}}
        before = brief.read_bytes()
        self.assertEqual(projection.call("swarm_project_tickets", request)["code"], "PROJECT_CODE_REQUIRED")
        self.assertEqual(brief.read_bytes(), before)
        self.assertFalse(projection._app.progress_ledger._state.path.exists())
        request["project_code"] = "abcd"
        result = projection.call("swarm_project_tickets", request)
        self.assertTrue(result["ok"])
        self.assertEqual(next(r for r in result["records"] if r["id"] == "proof-ticket")["display_id"], "ABCD-1")
        saved = brief.read_bytes()
        ledger = projection._app.progress_ledger._state.path.read_bytes()
        projection._app = App(fixture.codex_home, fixture.config, auto_bridge=transport)
        self.assertTrue(projection.call("swarm_project_tickets", request)["replayed"])
        self.assertEqual(brief.read_bytes(), saved)
        self.assertEqual(projection._app.progress_ledger._state.path.read_bytes(), ledger)
        self.assertEqual(projection.call("swarm_project_tickets", {**request, "changes": {"label": "Changed"}})["state"], "CONFLICT")
        self.assertEqual(projection.call("swarm_project_tickets", {**request, "project_code": "ABCDE"})["code"], "PROJECT_CODE_INVALID")
        self.assertEqual(projection.call("swarm_project_tickets", {**request, "acknowledge": True, "collection": "blocks", "record_id": "orphan",
            "expected_digest": result["source_digest"]})["state"], "REJECTED")
        self.assertEqual(brief.read_bytes(), saved)
        self.assertEqual(projection._app.progress_ledger._state.path.read_bytes(), ledger)
        self.assertEqual(transport.mock_calls, [])

    def test_library_mcp_save_readback_restart_and_invalid_write(self):
        sys.path.insert(0, str(mcp.REPO_ROOT))
        from console.server import App
        from console.tests.test_console import SwarmConsoleTests
        from console.tests.test_project_model_views import project_fixture, markdown_fixture
        fixture = SwarmConsoleTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        brief = fixture.alpha_root / "SWARM.md"
        brief.write_text(markdown_fixture(project_fixture("alpha")), encoding="utf-8")
        bridge = Mock()
        app = App(fixture.codex_home, fixture.config, auto_bridge=bridge)
        projection = mcp.SwarmProjection()
        projection._app = app
        scope = {"project_id":"project:alpha", "kind":"ROLE"}
        initial = projection.call("swarm_library_read", scope)
        self.assertEqual(len(initial["inventory"]["roles"]), 24)
        saved = projection.call("swarm_flow_save", {"project_id":"project:alpha",
            "expected_digest":initial["source_digest"], "definition":initial["starter"], "acknowledge":True})
        role = next(r for r in initial["inventory"]["roles"] if r["id"] == "manager")
        flow = saved["definitions"][0]
        assignment = dict(version=1, subject_kind="ROLE", subject_id="manager", subject_version=role["active_version"],
            ctrl_id=None, flow_id=flow["id"], flow_version=flow["version"], flow_digest=flow["digest"],
            label="My manager", notes="Planning note", repeat_count=2)
        request = dict(project_id="project:alpha", expected_digest=saved["source_digest"], acknowledge=True, assignment=assignment)
        assigned = projection.call("swarm_flow_assign", request)
        before = brief.read_bytes()
        projection._app = App(fixture.codex_home, fixture.config, auto_bridge=bridge)
        readback = projection.call("swarm_library_read", scope)
        self.assertEqual(readback["assignments"], assigned["assignments"])
        self.assertEqual(readback["source_digest"], assigned["source_digest"])
        self.assertEqual(projection.call("swarm_flow_assign", request)["state"], "CONFLICT")
        for change in ({"acknowledge":False}, {"acknowledge":1}, {"path":"elsewhere"}):
            with self.assertRaises(mcp.MCPError):
                projection.call("swarm_flow_assign", {**request, **change})
        rejected = projection.call("swarm_flow_assign", {**request, "expected_digest":assigned["source_digest"],
            "assignment":{**assignment, "version":2, "repeat_count":0}})
        self.assertEqual(rejected["state"], "REJECTED")
        self.assertFalse(rejected["ok"])
        self.assertEqual(brief.read_bytes(), before)
        self.assertEqual(bridge.mock_calls, [])
        # The real MCP wire marks conflicts as errors and retains structured scope.
        wire = {"jsonrpc":"2.0", "id":1, "method":"tools/call", "params":{"name":"swarm_flow_assign", "arguments":request}}
        with patch.object(mcp.SwarmProjection, "_load_app", return_value=projection._app), patch.object(sys, "stdin", io.StringIO(json.dumps(wire))), patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            mcp.serve(telemetry_path=fixture.root / "mcp-test.jsonl")
        result = json.loads(output.getvalue())["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(result["structuredContent"]["state"], "CONFLICT")
        self.assertEqual(result["structuredContent"]["project_id"], "project:alpha")
        event = json.loads((fixture.root / "mcp-test.jsonl").read_text().splitlines()[-1])
        self.assertFalse(event["success"])
        self.assertNotIn("Planning note", json.dumps(event))

        wire["params"]["arguments"] = {**request, "expected_digest":assigned["source_digest"],
            "assignment":{**assignment, "version":2, "label":"\ud800"}}
        with patch.object(mcp.SwarmProjection, "_load_app", return_value=projection._app), patch.object(sys, "stdin", io.StringIO(json.dumps(wire))), patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            mcp.serve(telemetry_path=fixture.root / "mcp-test.jsonl")
        result = json.loads(output.getvalue())["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(result["structuredContent"]["state"], "REJECTED")
        self.assertEqual(brief.read_bytes(), before)
        self.assertNotIn("ud800", (fixture.root / "mcp-test.jsonl").read_text())

    def test_existing_settings_unavailable_is_not_promoted_to_library_error(self):
        app = Mock()
        app.config_projection.return_value = {"ok": False, "state": "UNAVAILABLE"}
        wire = {"jsonrpc":"2.0", "id":1, "method":"tools/call",
            "params":{"name":"swarm_settings_read", "arguments":{}}}
        with tempfile.TemporaryDirectory() as directory, patch.object(mcp.SwarmProjection, "_load_app", return_value=app), patch.object(sys, "stdin", io.StringIO(json.dumps(wire))), patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            mcp.serve(telemetry_path=Path(directory) / "events.jsonl")
        result = json.loads(output.getvalue())["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"], {"ok":False, "state":"UNAVAILABLE"})

    @contextmanager
    def support_resource(self, root, body):
        """Exercise the real pinned image admission with an isolated template."""
        names = list(mcp.PROJECTS_ASSETS)
        files = {names[0]: ('<!doctype html><style>__CSS__</style><body>' + body + '<script type="module">__SCRIPT__</script></body>').encode(),
                 names[1]: b'body{color:black}', names[2]: (mcp.REPO_ROOT / names[2]).read_bytes()}
        for name, _, digest in mcp.PROJECTS_SUPPORT_IMAGES.values():
            files[name] = (mcp.REPO_ROOT / name).read_bytes()
            self.assertEqual(hashlib.sha256(files[name]).hexdigest(), digest)
        for name, _, digest, size in mcp.PROJECTS_PUBLIC_IMAGES.values():
            files[name] = (mcp.REPO_ROOT / name).read_bytes()
            self.assertEqual(len(files[name]), size)
            self.assertEqual(hashlib.sha256(files[name]).hexdigest(), digest)
        for name, payload in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        pins = {name: hashlib.sha256(files[name]).hexdigest() for name in names}
        path, digest, _ = self.hq_export(root)
        with patch.object(mcp, 'REPO_ROOT', root), patch.dict(mcp.PROJECTS_ASSETS, pins, clear=True):
            yield mcp.HQApp(path, digest, projects=True)

    def test_support_exact_images_admitted_without_snapshot_write(self):
        import base64
        self.assertEqual(mcp.PROJECTS_SUPPORT_IMAGES["__FLOWWWEB_LOGO_DARK__"],
                         ("skills/swarm/assets/ui/brand/flowwweb-lockup-v2-dark.svg", "image/svg+xml",
                          "cbc1bb458ab73cf7ac89972e7f087ae93a9a65902b1a4926b05484eaa90e9a11"))
        self.assertEqual(mcp.PROJECTS_SUPPORT_IMAGES["__FLOWWWEB_LOGO__"][2],
                         "57253bfef4d4f26c399dbb1d5fb2f258d663b52d31dd1414ab7c9cfef808d7b3")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = ''.join('<img src="' + token + '">' for token in mcp.PROJECTS_SUPPORT_IMAGES)
            with self.support_resource(root, body) as app:
                before = app.path.read_bytes()
                rendered = app.resource()['contents'][0]['text']
                for token, (name, mime, _) in mcp.PROJECTS_SUPPORT_IMAGES.items():
                    self.assertNotIn(token, rendered)
                    self.assertIn('data:' + mime + ';base64,' + base64.b64encode((root / name).read_bytes()).decode(), rendered)
                self.assertLessEqual(len(rendered.encode()), 1179648)
                self.assertEqual(before, app.path.read_bytes())
                self.assertEqual(app.uri, 'ui://swarm/hq/' + hashlib.sha256(rendered.encode()).hexdigest() + '.html')

    def test_support_missing_changed_and_oversized_images_fail_closed(self):
        for token, (name, _, _) in mcp.PROJECTS_SUPPORT_IMAGES.items():
            for failure in ('missing', 'changed', 'oversized'):
                with self.subTest(token=token, failure=failure), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    with self.support_resource(root, '<img src="' + token + '">') as app:
                        target = root / name
                        if failure == 'missing':
                            target.unlink()
                        else:
                            target.write_bytes(b'changed' if failure == 'changed' else b'x' * 524289)
                        with self.assertRaises((OSError, mcp.MCPError)):
                            app.resource()

    def test_support_unknown_badge_and_expanded_resource_limit_fail_closed(self):
        for body, error in (('<img src="__ROADTO1M_LOGO__">', 'unadmitted placeholder'),
                            ('<img src="__FLOWWWEB_LOGO__">' * 224, 'exceeds its bound')):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(mcp.MCPError, error):
                    with self.support_resource(Path(directory), body):
                        self.fail('Invalid resource was admitted')

    def test_compact_badge_uses_exact_public_url_and_only_resource_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.support_resource(Path(directory), '<footer><img src="__ROADTO1M_COMPACT__"></footer>') as app:
                resource = app.resource()['contents'][0]
                name, url, digest, _ = mcp.PROJECTS_COMPACT_BADGE
                self.assertIn('<footer><img src="' + url + '"></footer>', resource['text'])
                self.assertNotIn('__ROADTO1M_COMPACT__', resource['text'])
                self.assertNotIn('data:image/png;base64,', resource['text'])
                self.assertEqual(resource['_meta']['ui']['csp'], {'connectDomains': [], 'resourceDomains': ['https://flowwweb.com']})
                self.assertLessEqual(len(resource['text'].encode()), 1179648)
                # Remote provenance does not relax the ordinary inline image cap.
                with self.assertRaises(mcp.MCPError):
                    mcp._projects_asset(name, digest)

    def test_compact_badge_local_provenance_missing_or_changed_withholds_resource(self):
        for failure in ('missing', 'same_size_changed', 'short', 'growing'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with self.support_resource(root, '<img src="__ROADTO1M_COMPACT__">') as app:
                    name, _, _, size = mcp.PROJECTS_COMPACT_BADGE
                    target = root / name
                    if failure == 'missing':
                        target.unlink()
                    else:
                        target.write_bytes(b'x' * (size + {'same_size_changed': 0, 'short': -1, 'growing': 1}[failure]))
                    with self.assertRaises((OSError, mcp.MCPError)):
                        app.resource()

    def test_portrait_public_admission_preserves_exact_local_provenance_and_alt(self):
        token = '__SUPPORT_PORTRAIT__'
        name, url, digest, size = mcp.PROJECTS_PUBLIC_IMAGES[token]
        self.assertEqual(url, 'https://flowwweb.com/brand/swarm/support-caricature-light-20261024-18b223c6.webp')
        for failure in (None, 'missing', 'changed', 'short', 'growing'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with self.support_resource(root, '<img src="' + token + '" alt="Portrait unavailable">') as app:
                    target = root / name
                    before = target.read_bytes()
                    self.assertEqual(hashlib.sha256(before).hexdigest(), digest)
                    if failure:
                        if failure == 'missing':
                            target.unlink()
                        else:
                            target.write_bytes(b'x' * (size + {'changed': 0, 'short': -1, 'growing': 1}[failure]))
                        with self.assertRaises((OSError, mcp.MCPError)):
                            app.resource()
                    else:
                        resource = app.resource()['contents'][0]
                        self.assertIn('<img src="' + url + '" alt="Portrait unavailable">', resource['text'])
                        self.assertNotIn('data:image/webp;base64,', resource['text'])
                        self.assertEqual(resource['_meta']['ui']['csp'],
                                         {'connectDomains': [], 'resourceDomains': ['https://flowwweb.com']})
                        self.assertEqual(before, target.read_bytes())

    def test_selected_project_preserves_retained_ticket_fields_only_in_its_scope(self):
        row = {"id": "host-task", "project_id": "project-a", "state": "active",
               "display_id": "SWRM-1", "label": "Retained task name", "private": "omit"}
        view = {"overview_metrics": {"accepted_scope_id": "project-a", "accepted_cursor": {"digest": "bound"}},
                "progress": {"task_identity": {"digest": "ledger-bound"}, "projects": {
                    "project-a": {"tasks": [row]}, "project-b": {"tasks": [{**row, "project_id": "project-b"}]}}}}
        view["progress"]["all_projects"] = {"tasks": [row]}
        view["progress"]["controllers"] = {"ctrl-a": {"tasks": [row]}}
        result = mcp._compact_overview(view)
        self.assertEqual(result["progress"]["projects"]["project-a"]["tasks"], [{k: v for k, v in row.items() if k != "private"}])
        self.assertNotIn("tasks", result["progress"]["projects"]["project-b"])
        self.assertEqual(result["progress"]["task_identity"], {"digest": "ledger-bound"})
        for selected in ("project-a", "all"):
            view["overview_metrics"]["accepted_scope_id"] = selected
            compact = mcp._compact_overview(view)["progress"]
            for aggregate in (compact["all_projects"], compact["controllers"]["ctrl-a"]):
                self.assertEqual(aggregate["tasks"], [{k: v for k, v in row.items() if k not in {"private", "display_id", "label"}}])
        view["overview_metrics"]["accepted_scope_id"] = "all"
        self.assertTrue(all("tasks" not in scope for scope in mcp._compact_overview(view)["progress"]["projects"].values()))

    def test_projects_shell_composes_settings_without_rewriting_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path, digest, _ = self.hq_export(Path(directory))
            before = path.read_bytes()
            app = mcp.HQApp(path, digest, projects=True)
            rendered = app.render()
            self.assertIn('id="all-projects"', rendered)
            self.assertIn('id="settings"', rendered)
            self.assertIn('data:image/png;base64,', rendered)
            self.assertNotIn('__WORDMARK__', rendered)
            self.assertNotIn('__SCRIPT__', rendered)
            self.assertEqual(rendered.count('data-swarm-mcp-sdk='), 1)
            self.assertLessEqual(len(rendered.encode()), 1179648)
            self.assertEqual(app.uri, 'ui://swarm/hq/' + hashlib.sha256(rendered.encode()).hexdigest() + '.html')
            self.assertEqual(path.read_bytes(), before)
            key = next(iter(mcp.PROJECTS_ASSETS))
            with patch.dict(mcp.PROJECTS_ASSETS, {key: '0' * 64}), self.assertRaisesRegex(mcp.MCPError, 'identity mismatch'):
                app.render()

    def test_settings_bridge_uses_existing_config_authority_and_exact_retry(self):
        projection = mcp.SwarmProjection()
        app = Mock()
        projection._app = app
        scope = {"kind": "project", "project_id": "project-a", "accepted_cursor": "cursor-a"}
        app.config_projection.return_value = {"scope": scope, "revision": "a" * 64}
        self.assertEqual(projection.call("swarm_settings_read", {"scope": scope}), app.config_projection.return_value)
        app.config_projection.assert_called_once_with(scope)
        request = {"scope": scope, "expected_revision": "a" * 64, "acknowledge": True,
                   "text": '[execution]\nfast_mode = true\n', "operation_id": "settings-one"}
        app.update_config_source.return_value = {"accepted": True, "receipt": {"operation_id": "settings-one"}}
        self.assertEqual(projection.call("swarm_settings_save", request), app.update_config_source.return_value)
        projection.call("swarm_settings_save", dict(request))
        self.assertEqual(app.update_config_source.call_count, 2)
        self.assertEqual(app.update_config_source.call_args_list[0], app.update_config_source.call_args_list[1])
        for patch_value in ({"acknowledge": False}, {"acknowledge": 1}, {"scope": "global"}, {"operation_id": ""}, {"extra": True}):
            with self.subTest(patch_value=patch_value), self.assertRaises(mcp.MCPError):
                projection.call("swarm_settings_save", {**request, **patch_value})
        self.assertEqual(app.update_config_source.call_count, 2)
        app.update_config_source.side_effect = ValueError("stale revision")
        with self.assertRaisesRegex(ValueError, "stale revision"):
            projection.call("swarm_settings_save", request)

    def hq_export(self, root, **changes):
        html = '<!doctype html><title>Contract fixture only</title>'
        value = {"status": "READY_SOURCE_BOUND_SPACE_HTML_NOT_PUBLISHED", "html": html,
                 "html_sha256": hashlib.sha256(html.encode()).hexdigest(), "size_bytes": len(html.encode()),
                 "snapshot_digest": "sha256:" + "1" * 64, "approval_verified": False, "destination": None}
        value.update(changes)
        path = root / "export.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path, hashlib.sha256(path.read_bytes()).hexdigest(), value

    def test_hq_resource_read_accepts_protocol_meta_and_reports_only_stale_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            path, digest, _ = self.hq_export(Path(directory))
            app = mcp.HQApp(path, digest)
            expected = app.uri[len("ui://swarm/hq/"):-len(".html")]
            stale = "a" * 64
            cases = [
                {"uri": app.uri},
                {"uri": app.uri, "_meta": {"progressToken": "META-SECRET", "openai/widget": {"nested": [1]}}},
                {"uri": app.uri, "_meta": {}},
                {"uri": app.uri, "_meta": None},
                {"uri": app.uri, "_meta": "META-SECRET"},
                {"uri": app.uri, "_meta": ["META-SECRET"]},
                {"uri": app.uri, "FIELD-SECRET": 1},
                {"_meta": {}},
                {"uri": 7},
                {"uri": f"ui://swarm/hq/{stale}.html", "_meta": {"progressToken": "META-SECRET"}},
                {"uri": f"ui://swarm/hq/{stale.upper()}.html"},
                {"uri": f"ui://swarm/hq/{stale}.html?URI-SECRET"},
                {"uri": "file:///URI-SECRET"},
            ]
            lines = [json.dumps({"jsonrpc": "2.0", "id": index, "method": "resources/read", "params": params})
                     for index, params in enumerate(cases)]
            before = path.read_bytes()
            with patch.object(mcp.SwarmProjection, "_load_app", side_effect=AssertionError("no host load")), \
                    patch.object(mcp, "_telemetry", side_effect=AssertionError("no telemetry write")), \
                    patch.object(sys, "stdin", io.StringIO("\n".join(lines))), \
                    patch.object(sys, "stdout", new_callable=io.StringIO) as output:
                self.assertEqual(mcp.serve(hq_app=app), 0)
            rows = {row["id"]: row for row in map(json.loads, output.getvalue().splitlines())}
            self.assertEqual(len(rows), len(cases))
            served = rows[0]["result"]
            self.assertEqual(served["contents"][0]["uri"], app.uri)
            self.assertEqual(hashlib.sha256(served["contents"][0]["text"].encode()).hexdigest(), expected)
            for index in (1, 2):
                self.assertEqual(rows[index]["result"], served)
            for index in (3, 4, 5, 6, 7, 8):
                self.assertEqual(rows[index]["error"], {"code": -32602, "message": "invalid HQ resource request"})
            self.assertEqual(rows[9]["error"], {"code": -32602, "message": "stale HQ resource identity",
                                                "data": {"expected_sha256": expected, "received_sha256": stale}})
            for index in (10, 11, 12):
                self.assertEqual(rows[index]["error"], {"code": -32602, "message": "unknown HQ resource"})
            errors = "".join(json.dumps(rows[index]) for index in range(3, len(cases)))
            for secret in ("META-SECRET", "FIELD-SECRET", "URI-SECRET", "progressToken", "openai/widget", stale.upper()):
                self.assertNotIn(secret, errors)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [path])

        unbound = {"jsonrpc": "2.0", "id": 1, "method": "resources/read",
                   "params": {"uri": f"ui://swarm/hq/{'b' * 64}.html", "_meta": {}}}
        with patch.object(mcp, "_telemetry", side_effect=AssertionError("no telemetry write")), \
                patch.object(sys, "stdin", io.StringIO(json.dumps(unbound))), \
                patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            self.assertEqual(mcp.serve(), 0)
        self.assertEqual(json.loads(output.getvalue())["error"], {"code": -32602, "message": "unknown HQ resource"})

    def test_hq_resource_uses_exact_export_without_host_access_or_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            path, digest, value = self.hq_export(Path(directory))
            app = mcp.HQApp(path, digest)
            requests = [("initialize", {}), ("tools/list", {}), ("resources/list", {}),
                        ("resources/read", {"uri": app.uri}), ("tools/call", {"name": "swarm_hq_view"}),
                        ("resources/read", {"uri": "file:///private"}),
                        ("tools/call", {"name": "swarm_hq_view", "arguments": {"path": "private"}})]
            lines = [json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) for i, (method, params) in enumerate(requests)]
            before = path.read_bytes()
            with patch.object(mcp.SwarmProjection, "_load_app", side_effect=AssertionError("no host load")), patch.object(mcp, "_telemetry", side_effect=AssertionError("no telemetry write")), patch.object(sys, "stdin", io.StringIO("\n".join(lines))), patch.object(sys, "stdout", new_callable=io.StringIO) as output:
                self.assertEqual(mcp.serve(hq_app=app), 0)
            rows = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertIn("resources", rows[0]["result"]["capabilities"])
            self.assertEqual(rows[1]["result"]["tools"][:9], list(mcp.TOOLS))
            self.assertEqual(len(rows[1]["result"]["tools"]), 10)
            tool = rows[1]["result"]["tools"][-1]
            self.assertEqual(tool["name"], "swarm_hq_view")
            self.assertEqual(tool["_meta"], {"ui": {"resourceUri": app.uri}, "openai/ui": {"entrypoints": [{"type": "global"}, {"type": "thread"}]}})
            self.assertEqual(rows[2]["result"]["resources"][0]["uri"], app.uri)
            resource = rows[3]["result"]["contents"][0]
            self.assertTrue(resource["text"].startswith(value["html"]))
            self.assertIn('data-swarm-mcp-sdk="' + mcp.HQ_SDK_SHA256, resource["text"])
            served_digest = hashlib.sha256(resource["text"].encode()).hexdigest()
            self.assertEqual(app.uri, f"ui://swarm/hq/{served_digest}.html")
            # The Page/export cap remains 256 KiB; the separate adapted MCP resource is bounded at 1 MiB.
            self.assertGreater(len(resource["text"].encode()), 262144)
            self.assertLessEqual(len(resource["text"].encode()), 1048576)
            self.assertEqual(resource["mimeType"], "text/html;profile=mcp-app")
            self.assertEqual(resource["_meta"]["ui"]["csp"], {"connectDomains": [], "resourceDomains": []})
            self.assertEqual(rows[4]["result"]["structuredContent"]["snapshot_digest"], value["snapshot_digest"])
            self.assertFalse(rows[4]["result"]["structuredContent"]["approval_verified"])
            self.assertFalse(rows[4]["result"]["structuredContent"]["live"])
            self.assertEqual(rows[4]["result"]["structuredContent"]["served_html_sha256"], served_digest)
            self.assertEqual(rows[4]["result"]["structuredContent"]["refresh"], "PINNED_SNAPSHOT_REEXPORT_REQUIRED")
            self.assertEqual(rows[5]["error"]["code"], -32602)
            self.assertTrue(rows[6]["result"]["isError"])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_hq_sdk_and_resource_identity_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, digest, _ = self.hq_export(root)
            app = mcp.HQApp(path, digest)
            sdk = root / "sdk.js"
            sdk.write_bytes(b"changed")
            with patch.object(mcp, "HQ_SDK_PATH", sdk), self.assertRaisesRegex(mcp.MCPError, "SDK changed"):
                app.resource()
            with patch.object(mcp, "HQ_SDK_PATH", root / "missing.js"), self.assertRaises(OSError):
                app.result()
            sdk.write_bytes(b"</script>")
            with patch.object(mcp, "HQ_SDK_PATH", sdk), patch.object(mcp, "HQ_SDK_SHA256", hashlib.sha256(sdk.read_bytes()).hexdigest()), self.assertRaisesRegex(mcp.MCPError, "embedded"):
                app.resource()

    def test_hq_changed_missing_and_invalid_exports_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, digest, value = self.hq_export(root)
            app = mcp.HQApp(path, digest)
            with self.assertRaises(mcp.MCPError):
                mcp.HQApp(path, "wrong")
            path.write_text("changed", encoding="utf-8")
            with self.assertRaises(mcp.MCPError):
                app.resource()
            for changes in ({"html_sha256": "0" * 64}, {"size_bytes": 1}, {"approval_verified": True},
                            {"destination": "invented"}, {"snapshot_digest": "missing"},
                            {"status": "READY"}, {"html": "x" * 262145}):
                with self.subTest(changes=list(changes)):
                    path, digest, _ = self.hq_export(root, **changes)
                    with self.assertRaises(mcp.MCPError):
                        mcp.HQApp(path, digest)
            path.unlink()
            with self.assertRaises(OSError):
                app.result()

    def test_hq_optional_capability_does_not_change_default_tools_or_resources(self):
        requests = [{"jsonrpc": "2.0", "id": i, "method": method} for i, method in enumerate(("initialize", "tools/list", "resources/list"))]
        with patch.object(sys, "stdin", io.StringIO("\n".join(map(json.dumps, requests)))), patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            mcp.serve()
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertNotIn("resources", rows[0]["result"]["capabilities"])
        self.assertEqual(rows[1]["result"]["tools"], list(mcp.TOOLS))
        self.assertEqual(rows[2]["result"], {"resources": []})

    def test_all_projection_tools_use_existing_app(self) -> None:
        app = Mock()
        app.overview.return_value = {"nodes": [{"id": "task", "secret": "excluded"}], "projects": []}
        app.project_roster.return_value = {"projects": [{"id": "project"}], "current_work": {"state": "KNOWN", "available": True, "project_ids": ["project"], "projects": [{"id": "project"}], "controllers": [{"id": "ctrl"}]}}
        app.usage_history.return_value = {"hours": 24, "coverage": "local"}
        projection = mcp.SwarmProjection()
        projection._app = app
        self.assertEqual(projection.call("swarm_status", {"project_id": " project "})["nodes"], [{"id": "task"}])
        app.overview.assert_called_once_with("project")
        roster = projection.call("swarm_projects", {})
        self.assertEqual(roster["current_work"]["controllers"], [{"id": "ctrl"}])
        self.assertEqual(projection.call("swarm_usage", {})["coverage"], "local")
        app.usage_history.assert_called_once_with(hours=24, include_verified_yield=False)
        for name, arguments in [("unknown", {}), ("swarm_status", {"project_id": ""}), ("swarm_status", {"project_id": None}), ("swarm_usage", {"hours": True}), ("swarm_usage", {"hours": 2}), ("swarm_projects", {"unexpected": 1})]:
            with self.subTest(name=name, arguments=arguments), self.assertRaises(mcp.MCPError):
                projection.call(name, arguments)

    def test_stdio_invalid_requests_recover_and_errors_are_redacted(self) -> None:
        requests = ['{', '[]', 'null', '1', '{"jsonrpc":"2.0","id":[],"method":"tools/list"}']
        requests += [json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) for i, method, params in [
            (1, "initialize", []), (2, "tools/call", {"name": "swarm_status", "arguments": []}),
            (3, "tools/call", {"name": "swarm_status"}), (4, "tools/call", {"name": "swarm_projects"}),
            (5, "tools/call", {"name": "swarm_usage"}), (6, "tools/list", {}),
        ]]
        app = Mock()
        app.overview.side_effect = RuntimeError("SECRET credential path")
        app.project_roster.return_value = {"current_work": {}}
        app.usage_history.return_value = {"hours": 24}
        with tempfile.TemporaryDirectory() as directory, patch.object(mcp.SwarmProjection, "_load_app", return_value=app), patch.object(sys, "stdin", io.StringIO("\n".join(requests))), patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            telemetry = Path(directory) / "telemetry.jsonl"
            self.assertEqual(mcp.serve(telemetry_path=telemetry), 0)
            rows = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(rows[0]["error"]["code"], -32700)
            self.assertTrue(rows[7]["result"]["isError"])
            self.assertFalse(rows[8]["result"]["isError"])
            self.assertFalse(rows[9]["result"]["isError"])
            self.assertEqual(len(rows[-1]["result"]["tools"]), 9)
            self.assertNotIn("SECRET", output.getvalue() + telemetry.read_text())

    def test_output_cap_and_scratch_validation(self) -> None:
        usage = mcp._compact_usage({"items": [{"bucket_ms": i, "delta_tokens": 1} for i in range(300)],
                                   "total_tokens": 300, "window": {"after_ms": 0, "before_ms": 300},
                                   "task_history": {"items": ["detail"], "status": "PARTIAL"}, "verified_yield": {"detail": "omitted"}})
        self.assertEqual(len(usage["items"]), 256)
        self.assertTrue(usage["truncated"])
        self.assertEqual(usage["task_history"], {"status": "PARTIAL"})
        self.assertNotIn("verified_yield", usage)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, arguments in [("probe_write_file", {"name": "../outside", "content": "x"}), ("probe_write_file", {"content": "x" * 4097})]:
                with self.assertRaises(mcp.MCPError):
                    mcp._probe(root, name, arguments)
            (root / "probe.txt").write_text("x" * 4097)
            with self.assertRaises(mcp.MCPError):
                mcp._probe(root, "probe_read_file", {})
            request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "swarm_usage"}}
            with patch.object(mcp.SwarmProjection, "call", return_value={"large": "x" * 262144}), patch.object(sys, "stdin", io.StringIO(json.dumps(request))), patch.object(sys, "stdout", new_callable=io.StringIO) as output:
                mcp.serve(telemetry_path=root / "telemetry.jsonl")
                self.assertTrue(json.loads(output.getvalue())["result"]["isError"])
                self.assertLess(len(output.getvalue()), 1024)

    def test_compacted_usage_passes_actual_reader_without_losing_window_deltas(self):
        script = ("import fs from 'node:fs'; "
                  "import {usageView} from './skills/swarm/assets/ui/swarm-usage.mjs'; "
                  "const inputs=JSON.parse(fs.readFileSync(0,'utf8')); "
                  "console.log(JSON.stringify(inputs.map(value=>usageView(value,24))));")
        inputs = []
        for count in (0, 256, 257, 4097):
            items = [{"bucket_ms": 10 + i * 3, "delta_tokens": i % 7} for i in range(count)]
            view = {"ok": True, "hours": 24, "status": "partial" if count else "no_data",
                    "window": {"after_ms": 10, "before_ms": 13000}, "items": items,
                    "total_tokens": sum(row["delta_tokens"] for row in items),
                    "coverage": {"observed_threads": 1, "expected_threads": 2}}
            compact = mcp._compact_usage(view)
            self.assertEqual(compact, mcp._compact_usage(view))
            self.assertEqual(sum(row["delta_tokens"] for row in compact["items"]), view["total_tokens"])
            self.assertEqual(len(compact["items"]), min(count, 256))
            if count <= 256:
                self.assertEqual(compact["items"], items)
            else:
                self.assertEqual(compact["series_aggregation"]["input_count"], count)
                self.assertEqual(compact["items"][-1]["bucket_ms"], items[-1]["bucket_ms"])
                self.assertTrue(all(row["bucket_ms"] in {item["bucket_ms"] for item in items} for row in compact["items"]))
            inputs.append(compact)
        run = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT.parents[1],
                             input=json.dumps(inputs), text=True, capture_output=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        for original, rendered in zip(inputs, json.loads(run.stdout)):
            self.assertEqual(rendered["total"], original["total_tokens"] if original["items"] else None)
            self.assertEqual(rendered["coverage"], original["coverage"])
            self.assertEqual(rendered["window"], original["window"])
            self.assertEqual(rendered["status"], original["status"])

    def test_project_usage_forwards_exact_scope_only_when_requested(self):
        spec = next(tool for tool in mcp.TOOLS if tool["name"] == "swarm_usage")
        self.assertEqual(spec["inputSchema"]["properties"]["project_id"], {"type": "string"})
        self.assertFalse(spec["inputSchema"]["additionalProperties"])
        app = Mock()
        projection = mcp.SwarmProjection()
        projection._app = app
        app.usage_history.return_value = {"hours": 168, "scope": {"type": "all-projects"}}
        self.assertEqual(projection.call("swarm_usage", {"hours": 168})["scope"], {"type": "all-projects"})
        app.usage_history.assert_called_once_with(hours=168, include_verified_yield=False)
        for arguments, hours in (({"project_id": " project-a "}, 24), ({"project_id": "project-a", "hours": 720}, 720)):
            with self.subTest(arguments=arguments):
                app.usage_history.reset_mock()
                app.usage_history.return_value = {"hours": hours, "scope": {"type": "project", "project_id": "project-a"}}
                result = projection.call("swarm_usage", arguments)
                app.usage_history.assert_called_once_with(project_id="project-a", hours=hours, include_verified_yield=False)
                self.assertEqual(result["scope"], {"type": "project", "project_id": "project-a"})
        app.usage_history.reset_mock()
        for arguments in ({"project_id": ""}, {"project_id": "   "}, {"project_id": None}, {"project_id": 7},
                          {"project_id": ["project-a"]}, {"project_id": "project-a", "ctrl_id": "ctrl-a"},
                          {"project_id": "project-a", "hours": 2}, {"project_id": "project-a", "hours": True}):
            with self.subTest(arguments=arguments), self.assertRaises(mcp.MCPError):
                projection.call("swarm_usage", arguments)
        app.usage_history.assert_not_called()
        for returned in ({"type": "project", "project_id": "project-b"}, {"type": "all-projects"},
                         {"type": "project", "project_id": " project-a "}, "project-a", None):
            with self.subTest(returned=returned):
                app.usage_history.return_value = {"hours": 24, **({} if returned is None else {"scope": returned})}
                with self.assertRaisesRegex(mcp.MCPError, "scope mismatch"):
                    projection.call("swarm_usage", {"project_id": "project-a"})

    def test_project_usage_compaction_passes_scoped_reader_and_rejects_leakage(self):
        script = ("import fs from 'node:fs'; "
                  "import {usageView} from './skills/swarm/assets/ui/swarm-usage.mjs'; "
                  "const cases=JSON.parse(fs.readFileSync(0,'utf8')); "
                  "console.log(JSON.stringify(cases.map(([value,project])=>{try{return {ok:true,view:project===null?usageView(value,24):usageView(value,24,project)};}catch{return {ok:false};}})));")

        def view(count, scope, status=None):
            items = [{"bucket_ms": 10 + i * 3, "delta_tokens": i % 7} for i in range(count)]
            return {"ok": True, "hours": 24, "status": status or ("partial" if count else "no_data"),
                    "window": {"after_ms": 10, "before_ms": 13000}, "items": items,
                    "total_tokens": sum(row["delta_tokens"] for row in items),
                    "coverage": {"observed_threads": 1, "expected_threads": 2}, "scope": scope}

        project_a = {"type": "project", "project_id": "project-a"}
        everyone = {"type": "all-projects"}
        cases = [(view(0, project_a), "project-a", True), (view(257, project_a), "project-a", True),
                 (view(257, project_a, "ok"), "project-a", True),
                 (view(257, {"type": "project", "project_id": "project-b"}), "project-a", False),
                 (view(257, everyone), "project-a", False), (view(257, project_a), None, False),
                 (view(257, everyone), None, True)]
        compacted = []
        for value, project, _ in cases:
            compact = mcp._compact_usage(value)
            self.assertEqual(compact["scope"], value["scope"])
            self.assertEqual(sum(row["delta_tokens"] for row in compact["items"]), value["total_tokens"])
            compacted.append([compact, project])
        run = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT.parents[1],
                             input=json.dumps(compacted), text=True, capture_output=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        for (value, project, accepted), rendered in zip(cases, json.loads(run.stdout)):
            with self.subTest(project=project, scope=value["scope"], count=len(value["items"])):
                self.assertEqual(rendered["ok"], accepted)
                if accepted:
                    self.assertEqual(rendered["view"]["total"], value["total_tokens"] if value["items"] else None)
                    self.assertEqual(rendered["view"]["window"], value["window"])
                    self.assertEqual(rendered["view"]["status"], value["status"])
                    self.assertEqual(rendered["view"]["coverage"], value["coverage"])

    def test_usage_aggregation_does_not_hide_invalid_observations(self):
        for field, value in (("bucket_ms", 0), ("bucket_ms", 9999), ("bucket_ms", True),
                             ("delta_tokens", -1), ("delta_tokens", True)):
            rows = [{"bucket_ms": i, "delta_tokens": 1} for i in range(257)]
            rows[10][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(mcp.MCPError):
                mcp._compact_usage({"items": rows, "total_tokens": 257,
                                    "window": {"after_ms": 0, "before_ms": 300}})
        with self.assertRaises(mcp.MCPError):
            mcp._compact_usage({"items": [{"bucket_ms": i, "delta_tokens": 1} for i in range(257)],
                                "total_tokens": 256, "window": {"after_ms": 0, "before_ms": 300}})

    def test_probe_read_write_delete_are_local_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = subprocess.Popen(
                [sys.executable, str(SERVER), "--stdio", "--probe-root", str(root), "--telemetry", str(root / "telemetry.jsonl")],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8",
            )
            try:
                initialized = call(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
                self.assertEqual(initialized["result"]["serverInfo"]["name"], "swarm-mcp")
                listed = call(process, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
                names = {tool["name"] for tool in listed["result"]["tools"]}
                self.assertTrue({"probe_read_file", "probe_write_file", "probe_delete_file"} <= names)
                written = call(process, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "probe_write_file", "arguments": {"name": "probe.txt", "content": "ok"}}})
                self.assertFalse(written["result"]["isError"])
                self.assertEqual((root / "probe.txt").read_text(encoding="utf-8"), "ok")
                read = call(process, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "probe_read_file", "arguments": {"name": "probe.txt"}}})
                self.assertIn('"content":"ok"', read["result"]["content"][0]["text"])
                deleted = call(process, {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "probe_delete_file", "arguments": {"name": "probe.txt"}}})
                self.assertFalse(deleted["result"]["isError"])
                self.assertFalse((root / "probe.txt").exists())
                self.assertGreaterEqual(len((root / "telemetry.jsonl").read_text(encoding="utf-8").splitlines()), 3)
            finally:
                if process.stdin:
                    process.stdin.close()
                if process.stdout:
                    process.stdout.close()
                process.kill()
                process.wait(timeout=5)



if __name__ == "__main__":
    unittest.main()
