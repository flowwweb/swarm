from __future__ import annotations

import copy
import concurrent.futures
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path


CONSOLE_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


views = load_module("tested_project_model_views", CONSOLE_ROOT / "project_model_views.py")
server = load_module("tested_project_model_views_registry", CONSOLE_ROOT / "server.py")


def project_fixture(project_id, **updates):
    model = {
        "schema_version": 1,
        "updated_at": "2026-08-31T00:00:00Z",
        "project": {"id": project_id, "purpose": f"Sanitized {project_id} project"},
        "users_outcomes": [f"Use {project_id} truthfully"],
        "objective": {"current": f"Advance {project_id}", "ranked_outcomes": []},
        "repo": {"canonical_root": "."},
        "authority": {"ctrl_id": f"ctrl-{project_id}"},
        "milestones": [{"id": f"m-{project_id}", "state": "active"}],
        "decisions": [{"id": f"d-{project_id}", "decision": "Keep one Markdown authority"}],
        "ownership": {"active_ctrl_id": f"ctrl-{project_id}", "active_lead_ids": []},
        "proof_acceptance": {"claim_limit": "Source/local only"},
        "risks_blockers": [],
        "links": [],
    }
    model.update(updates)
    return model


REAL_PROJECT_FIXTURES = {
    "Helm": project_fixture("helm", milestones=[{"id": "m-collaboration", "state": "waiting"}]),
    "Nemo": project_fixture(
        "nemo",
        objective={"current": "Qualify Android routing", "ranked_outcomes": [{"id": "o-routing", "rank": 1, "milestone_id": "m-routing"}]},
        milestones=[{"id": "m-routing", "state": "active", "task_ids": ["t-device"]}],
        tasks=[{"id": "t-device", "state": "waiting", "blocker_ids": ["b-device"]}],
        risks_blockers=[{"id": "b-device", "state": "waiting", "affected_ids": ["t-device"]}],
        artifacts=[{"id": "a-routing", "revision": "3d23f5bd", "proof_class": "SOURCE_STATIC"}],
        proposed_lens_ids=["lens-overview-health", "lens-roadmap-milestones", "lens-tasks-kanban"],
    ),
    "RightWork": project_fixture("rightwork", milestones=[{"id": "m-feed", "state": "review-gated"}]),
    "SWARM": project_fixture("swarm", milestones=[{"id": "m-dogfood", "state": "blocked"}], blocks=[{"id": "block-guard", "state": "blocked"}]),
}


def markdown_fixture(document):
    return "# Project brief\n\n<!-- swarm-project-brief:schema=1 -->\n```json\n" + json.dumps(document, indent=2) + "\n```\n\nRetained prose.\n"


def fixture(**updates):
    model = {
        "schema_version": 1,
        "project": {"id": "fixture", "purpose": "Truthful fixture"},
        "objective": {"current": "Ship the fixture", "ranked_outcomes": [{"id": "o-1", "rank": 1, "outcome": "Accepted fixture", "milestone_id": "m-1", "dependency_ids": ["a-1"]}]},
        "milestones": [{"id": "m-1", "rank": 1, "task_ids": ["t-1"], "dependency_ids": ["a-1"], "blocker_ids": ["r-1"]}],
        "tasks": [{"id": "t-1", "owner_id": "agent-1", "dependency_ids": ["a-1"], "blocker_ids": ["r-1"]}],
        "risks_blockers": [{"id": "r-1", "affected_ids": ["t-1", "m-1"]}],
        "artifacts": [{"id": "a-1", "revision": "abc", "proof_class": "SOURCE_STATIC"}],
        "proof_acceptance": {"claim_limit": "Source/static only"},
        "authority": {"ctrl_id": "ctrl-1", "project_model_lead_id": "lead-1"},
        "ownership": {"active_ctrl_id": "ctrl-1", "active_lead_ids": ["lead-1"]},
        "proposed_lens_ids": list(views.LENS_VIEW_IDS),
    }
    model.update(updates)
    return model


def identity(model):
    digest = views._digest(model)
    artifact = views.ArtifactIdentity(f"project-brief:{model['project']['id']}", digest, "schema-1-project-model")
    return model, artifact


class ProjectModelViewsTests(unittest.TestCase):
    def test_explicit_work_selection_preserves_model_and_default(self):
        model = fixture()
        before = copy.deepcopy(model)
        def project(selection=None, artifact=None):
            return views.project_schema1_views(
                model, artifact or identity(model)[1], server.PROJECT_VIEW_RENDERERS,
                server.PROJECT_VIEW_ACTIONS, selected_lens_ids=selection,
            )
        self.assertEqual(project(), self.project(model))
        model.pop("proposed_lens_ids")
        self.assertEqual(project()["views"], [])
        work = project(["lens-tasks-kanban"])["views"]
        self.assertEqual([item["id"] for item in work], ["view.project.work"])
        self.assertEqual(work[0]["content"]["goal_associations"], [{"goal_id": "o-1", "milestone_id": "m-1"}])
        self.assertIn("/objective/ranked_outcomes", [source["pointer"] for source in work[0]["sources"]])
        self.assertEqual(model, {key: value for key, value in before.items() if key != "proposed_lens_ids"})
        for selection in ("lens-tasks-kanban", ["unknown"], ["lens-tasks-kanban"] * 2, [None], {}, [""]):
            with self.subTest(selection=selection), self.assertRaises(views.ProjectModelError):
                project(selection)
        with self.assertRaisesRegex(views.ProjectModelError, "digest does not match"):
            project(["lens-tasks-kanban"], identity(before)[1])
        self.assertEqual(project([])["views"], [])
        model["objective"]["ranked_outcomes"].append({"id": "o-2", "milestone_id": "m-1"})
        self.assertEqual(len(project(["lens-tasks-kanban"])["views"][0]["content"]["goal_associations"]), 2)
        model["objective"]["ranked_outcomes"][0]["milestone_id"] = "missing"
        self.assertTrue(any(item["code"] == "UNRESOLVED_GOAL_ASSOCIATION" for item in project(["lens-tasks-kanban"])["diagnostics"]))
        del model["objective"]["ranked_outcomes"]
        work = project(["lens-tasks-kanban"])["views"][0]
        self.assertNotIn("goal_associations", work["content"])
        self.assertNotIn("/objective/ranked_outcomes", [source["pointer"] for source in work["sources"]])
        model["objective"]["ranked_outcomes"] = "invalid"
        self.assertEqual(project(["lens-tasks-kanban"])["views"], [])

    def project(self, model):
        loaded, artifact = identity(model)
        return views.project_schema1_views(loaded, artifact, server.PROJECT_VIEW_RENDERERS, server.PROJECT_VIEW_ACTIONS)

    def test_six_existing_renderers_and_truthful_missing_blocks_progress(self):
        projection = self.project(fixture())
        self.assertEqual(
            [(tab["label"], tab["renderer"], tab["mode"]) for tab in projection["tabs"]],
            [
                ("Overview", "document", "blocks"),
                ("Roadmap", "timeline", "milestones"),
                ("Work", "table", "records"),
                ("Flow", "canvas", "network"),
                ("Artifacts", "gallery", "list"),
                ("Agents", "table", "records"),
            ],
        )
        work = projection["tabs"][2]["content"]
        self.assertEqual(work["blocks_state"], "UNKNOWN")
        self.assertEqual(work["progress_state"], "UNKNOWN")
        self.assertEqual([(row["id"], row["depth"]) for row in work["rows"]], [("m-1", 0), ("t-1", 1)])
        self.assertTrue(all(row["progress_percent"] is None for row in work["rows"]))

    def test_flow_relationships_and_artifact_associations_are_typed(self):
        projection = self.project(fixture())
        flow = projection["tabs"][3]["content"]
        edges = {(edge["source"], edge["target"], edge["type"]) for edge in flow["edges"]}
        self.assertIn(("m-1", "t-1", "contains"), edges)
        self.assertIn(("t-1", "a-1", "depends_on"), edges)
        self.assertIn(("r-1", "t-1", "blocks"), edges)
        self.assertIn(("o-1", "m-1", "targets"), edges)
        artifact = projection["tabs"][4]["content"]["artifacts"][0]
        self.assertEqual(artifact["associated_ids"], ["m-1", "t-1"])
        self.assertIsNone(artifact["action"])

    def test_work_rows_preserve_milestone_task_block_hierarchy(self):
        projection = self.project(fixture(blocks=[{
            "id": "b-1", "task_id": "t-1", "label": "Verified block", "progress_percent": 100,
        }]))
        work = projection["tabs"][2]["content"]
        self.assertEqual(
            [(row["id"], row["kind"], row["depth"], row["parent_id"]) for row in work["rows"]],
            [
                ("m-1", "milestone", 0, None),
                ("t-1", "task", 1, "m-1"),
                ("b-1", "block", 2, "t-1"),
            ],
        )
        self.assertEqual(work["blocks_state"], "KNOWN")
        self.assertEqual(work["progress_state"], "KNOWN")

    def test_artifact_action_requires_digest_bound_safe_ref(self):
        artifact = {
            "id": "a-1", "label": "APK", "proof_class": "LOCAL_ARTIFACT",
            "ref": "artifact://fixture/build/app.apk", "digest": "a" * 64,
        }
        projection = self.project(fixture(artifacts=[artifact]))
        action = projection["tabs"][4]["content"]["artifacts"][0]["action"]
        self.assertEqual(action["kind"], "open_artifact")
        self.assertEqual(action["digest"], "sha256:" + "a" * 64)
        artifact["ref"] = "artifact://other/../../secret"
        projection = self.project(fixture(artifacts=[artifact]))
        self.assertIsNone(projection["tabs"][4]["content"]["artifacts"][0]["action"])

    def test_duplicate_and_unknown_renderer_fail_closed(self):
        with self.assertRaisesRegex(views.ProjectModelError, "duplicate stable id"):
            self.project(fixture(tasks=[{"id": "m-1"}]))
        registry = dict(server.PROJECT_VIEW_RENDERERS)
        registry["canvas"] = frozenset({"spatial"})
        model, artifact = identity(fixture())
        with self.assertRaisesRegex(views.ProjectModelError, "does not admit canvas/network"):
            views.project_schema1_views(model, artifact, registry, server.PROJECT_VIEW_ACTIONS)
        foreign = views.ArtifactIdentity("project-brief:other", artifact.revision, artifact.purpose)
        with self.assertRaisesRegex(views.ProjectModelError, "belongs to another project"):
            views.project_schema1_views(model, foreign, server.PROJECT_VIEW_RENDERERS, server.PROJECT_VIEW_ACTIONS)
        forged = views.ArtifactIdentity(artifact.base, "f" * 64, artifact.purpose)
        with self.assertRaisesRegex(views.ProjectModelError, "digest does not match"):
            views.project_schema1_views(model, forged, server.PROJECT_VIEW_RENDERERS, server.PROJECT_VIEW_ACTIONS)

    def test_unresolved_relationship_is_diagnostic_not_fabricated_node(self):
        model = fixture(tasks=[{"id": "t-1", "dependency_ids": ["missing"]}])
        projection = self.project(model)
        self.assertEqual(projection["diagnostics"], [{
            "code": "UNRESOLVED_RELATIONSHIP", "source_id": "t-1", "target_id": "missing", "relation": "depends_on",
        }])
        node_ids = {node["id"] for node in projection["tabs"][3]["content"]["nodes"]}
        self.assertNotIn("missing", node_ids)

    def test_projection_is_deterministic_and_has_no_second_loader_or_renderer(self):
        model = fixture(tasks=[{"id": "t-1", "task_name": "Task", "owner_id": "agent-1"}])
        first = self.project(model)
        second = self.project(model)
        self.assertEqual(first["projection_digest"], second["projection_digest"])
        self.assertTrue(first["projection_digest"].startswith("sha256:"))
        self.assertTrue(all(tab["view_digest"].startswith("sha256:") for tab in first["tabs"]))
        self.assertEqual(first["tabs"][0]["sources"][0]["pointer"], "/objective")
        self.assertEqual(first["tabs"][0]["sources"][0]["digest"], "sha256:" + views._digest(model["objective"]))
        self.assertFalse(hasattr(views, "load_schema1_brief"))
        self.assertFalse(hasattr(views, "render_html"))
        self.assertFalse(hasattr(views, "main"))

    def test_lenses_are_conditional_ordered_and_unknown_ids_fail_closed(self):
        projection = self.project(fixture(proposed_lens_ids=[
            "lens-agents", "future-lens", "lens-overview-health",
        ]))
        self.assertEqual([tab["id"] for tab in projection["tabs"]], [
            "view.project.agents", "view.project.overview-health",
        ])
        self.assertEqual(projection["views"], projection["tabs"])
        self.assertEqual(projection["tab"], {"id": "ui", "label": "Workspace"})
        self.assertIn({"code": "UNKNOWN_LENS_WITHHELD", "lens_id": "future-lens"}, projection["diagnostics"])
        self.assertEqual(self.project(fixture(proposed_lens_ids=[]))["tabs"], [])

    def test_runtime_identity_and_composed_cursor_bind_every_source(self):
        model, artifact = identity(fixture(proposed_lens_ids=["lens-overview-health"]))
        runtime_id = "local-123"
        artifact = views.ArtifactIdentity(f"project-brief:{runtime_id}", artifact.revision, artifact.purpose)
        binding = {
            "project_id": runtime_id,
            "model_project_id": "fixture",
            "canonical_root": "C:/saved/fixture",
            "brief_bytes_digest": "sha256:" + "a" * 64,
            "source_digest": "sha256:" + views._digest(model),
            "project_briefs_cursor": {"type": "project_briefs_v1", "digest": "b" * 64},
            "locator": None,
        }
        projection = views.project_schema1_views(
            model, artifact, server.PROJECT_VIEW_RENDERERS, server.PROJECT_VIEW_ACTIONS,
            runtime_project_id=runtime_id, projection_binding=binding,
        )
        self.assertEqual((projection["project_id"], projection["model_project_id"]), (runtime_id, "fixture"))
        self.assertEqual(projection["projection_binding"], binding)
        self.assertRegex(projection["accepted_cursor"]["digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(projection["tabs"][0]["sources"][0]["source_digest"], r"^sha256:[0-9a-f]{64}$")
        stale = copy.deepcopy(binding)
        stale["project_briefs_cursor"] = {"type": "project_briefs_v1", "digest": "not-a-digest"}
        with self.assertRaisesRegex(views.ProjectModelError, "cursor is invalid"):
            views.project_schema1_views(
                model, artifact, server.PROJECT_VIEW_RENDERERS, server.PROJECT_VIEW_ACTIONS,
                runtime_project_id=runtime_id, projection_binding=stale,
            )

    def test_missing_historical_agent_fields_withhold_only_agents(self):
        model = fixture()
        del model["authority"]
        del model["ownership"]
        projection = self.project(model)
        self.assertEqual([tab["label"] for tab in projection["tabs"]], ["Overview", "Roadmap", "Work", "Flow", "Artifacts"])
        self.assertEqual(projection["diagnostics"], [{
            "code": "WITHHELD_VIEW",
            "view_id": "view.project.agents",
            "reason": "MISSING_OR_INVALID_SOURCE",
            "pointers": "/authority,/ownership",
        }])
        for field in ("authority", "ownership"):
            with self.subTest(field=field):
                model = fixture()
                model[field] = {}
                self.assertNotIn("Agents", [tab["label"] for tab in self.project(model)["tabs"]])

    def test_real_project_briefs_parse_and_round_trip_without_rewriting(self):
        for name, expected in REAL_PROJECT_FIXTURES.items():
            with self.subTest(project=name):
                text = markdown_fixture(expected)
                parsed, digest = views.parse_project_brief_markdown(text, project_id=expected["project"]["id"])
                self.assertEqual(parsed, expected)
                self.assertEqual(digest, "sha256:" + views._digest(expected))
                self.assertEqual(views.render_project_brief_markdown(text, parsed), text)
                self.assertEqual(parsed["objective"]["current"], expected["objective"]["current"])
                self.assertEqual(parsed["milestones"], expected["milestones"])
                self.assertEqual(parsed.get("tasks", []), expected.get("tasks", []))
                self.assertEqual(parsed.get("blocks", []), expected.get("blocks", []))
                self.assertEqual(parsed.get("proposed_lens_ids", []), expected.get("proposed_lens_ids", []))

    def test_controlled_edit_updates_one_existing_record_atomically(self):
        original = copy.deepcopy(REAL_PROJECT_FIXTURES["Nemo"])
        text = markdown_fixture(original)
        _, digest = views.parse_project_brief_markdown(text)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SWARM.md"
            path.write_text(text, encoding="utf-8")
            new_digest = views.update_project_brief(
                path,
                expected_digest=digest,
                collection="tasks",
                record_id="t-device",
                state=" active ",
                updated_at="2026-09-02T00:00:00Z",
            )
            updated_text = path.read_text(encoding="utf-8")
            updated, observed_digest = views.parse_project_brief_markdown(updated_text, project_id="nemo")
            self.assertEqual(new_digest, observed_digest)
            self.assertNotEqual(new_digest, digest)
            self.assertEqual(updated["tasks"][0]["state"], "active")
            self.assertEqual(updated["updated_at"], "2026-09-02T00:00:00Z")
            expected = copy.deepcopy(original)
            expected["tasks"][0]["state"] = "active"
            expected["updated_at"] = "2026-09-02T00:00:00Z"
            self.assertEqual(updated, expected)
            self.assertTrue(updated_text.startswith("# Project brief\n\n"))
            self.assertTrue(updated_text.endswith("\n\nRetained prose.\n"))
            self.assertEqual([item.name for item in Path(directory).iterdir()], ["SWARM.md"])
            before_conflict = path.read_bytes()
            with self.assertRaisesRegex(views.ProjectModelError, "digest conflict"):
                views.update_project_brief(
                    path,
                    expected_digest=digest,
                    collection="tasks",
                    record_id="t-device",
                    state="complete",
                    updated_at="2026-09-02T01:00:00Z",
                )
            self.assertEqual(path.read_bytes(), before_conflict)

    def test_schema1_lifecycle_create_update_reopen_and_restart(self):
        model = project_fixture(
            "fixture",
            objective={"current": "Ship", "ranked_outcomes": []},
            milestones=[],
            tasks=[],
            blocks=[],
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SWARM.md"
            path.write_text(markdown_fixture(model), encoding="utf-8")
            _, digest = views.parse_project_brief_markdown(path.read_text(encoding="utf-8"))
            operations = (
                ("goals", "g-1", {"label": "Goal", "state": "active", "milestone_id": "m-1"}),
                ("milestones", "m-1", {"label": "Milestone", "state": "active", "task_ids": ["t-1"]}),
                ("tasks", "t-1", {
                    "task_name": "Task", "state": "active", "milestone_ref": {"milestone_id": "m-1"},
                    "acceptance_criteria": ["Proof passes"], "artifact_ids": ["a-1"],
                }),
                ("blocks", "b-1", {"label": "Block", "state": "planned", "task_id": "t-1"}),
            )
            for collection, record_id, changes in operations:
                digest = views.mutate_project_brief(
                    path, expected_digest=digest, operation="create", collection=collection,
                    record_id=record_id, changes=changes, updated_at="2026-09-05T00:00:00Z",
                )
            digest = views.mutate_project_brief(
                path, expected_digest=digest, operation="update", collection="tasks", record_id="t-1",
                changes={"task_name": "Renamed", "state": " complete "}, updated_at="2026-09-05T00:01:00Z",
            )
            digest = views.mutate_project_brief(
                path, expected_digest=digest, operation="reopen", collection="tasks", record_id="t-1",
                changes={"state": "active"}, updated_at="2026-09-05T00:02:00Z",
            )

            restarted = load_module("restarted_project_model_views", CONSOLE_ROOT / "project_model_views.py")
            observed, observed_digest = restarted.parse_project_brief_markdown(path.read_text(encoding="utf-8"))
            task = observed["tasks"][0]
            self.assertEqual(observed_digest, digest)
            self.assertEqual(observed["objective"]["ranked_outcomes"][0]["id"], "g-1")
            self.assertEqual(task["task_name"], "Renamed")
            self.assertEqual(task["state"], "active")
            self.assertEqual(task["milestone_ref"], {"milestone_id": "m-1"})
            self.assertEqual(task["acceptance_criteria"], ["Proof passes"])
            self.assertEqual(task["artifact_ids"], ["a-1"])

    def test_schema1_lifecycle_rejects_duplicate_stale_and_invalid_reopen(self):
        model = project_fixture(
            "fixture",
            tasks=[{"id": "t-1", "state": "complete"}],
            blocks=[],
            artifacts=[{"id": "a-1", "revision": "abc", "proof_class": "SOURCE_STATIC"}],
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SWARM.md"
            path.write_text(markdown_fixture(model), encoding="utf-8")
            _, digest = views.parse_project_brief_markdown(path.read_text(encoding="utf-8"))
            digest = views.mutate_project_brief(
                path, expected_digest=digest, operation="update", collection="tasks", record_id="t-1",
                changes={"task_name": "Still closed"}, updated_at="2026-09-05T00:00:00Z",
            )
            digest = views.mutate_project_brief(
                path, expected_digest=digest, operation="update", collection="tasks", record_id="t-1",
                changes={"state": "accepted"}, updated_at="2026-09-05T00:01:00Z",
            )
            before = path.read_bytes()
            cases = (
                {"expected_digest": digest, "operation": "create", "collection": "blocks", "record_id": "t-1", "changes": {"state": "planned"}},
                {"expected_digest": digest, "operation": "create", "collection": "tasks", "record_id": "A-1", "changes": {"state": "planned"}},
                {"expected_digest": digest, "operation": "reopen", "collection": "tasks", "record_id": "t-1", "changes": {"state": " complete "}},
                {"expected_digest": digest, "operation": "update", "collection": "tasks", "record_id": "t-1", "changes": {"state": "active"}},
                {"expected_digest": digest, "operation": "update", "collection": "tasks", "record_id": "t-1", "changes": {"owner_id": "agent-1"}},
                {"expected_digest": digest, "operation": "update", "collection": "tasks", "record_id": "t-1", "changes": {"progress_percent": 50}},
                {"expected_digest": digest, "operation": "update", "collection": "tasks", "record_id": "t-1", "changes": {"acceptance_receipt": "forged"}},
                {"expected_digest": digest, "operation": "update", "collection": "tasks", "record_id": "t-1", "changes": {"state": None}},
                {"expected_digest": "sha256:" + "0" * 64, "operation": "update", "collection": "tasks", "record_id": "t-1", "changes": {"state": "complete"}},
            )
            for case in cases:
                with self.subTest(operation=case["operation"]), self.assertRaises(views.ProjectModelError):
                    views.mutate_project_brief(path, updated_at="2026-09-05T00:00:00Z", **case)
                self.assertEqual(path.read_bytes(), before)
            with self.assertRaisesRegex(views.ProjectModelError, "state is invalid"):
                views.update_project_brief(
                    path, expected_digest=digest, collection="tasks", record_id="t-1",
                    state=None, updated_at="2026-09-05T00:00:00Z",
                )
            self.assertEqual(path.read_bytes(), before)

    def test_concurrent_expected_digest_update_has_one_winner(self):
        text = markdown_fixture(REAL_PROJECT_FIXTURES["Nemo"])
        _, digest = views.parse_project_brief_markdown(text)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SWARM.md"
            path.write_text(text, encoding="utf-8")

            def update(state):
                return views.update_project_brief(
                    path,
                    expected_digest=digest,
                    collection="tasks",
                    record_id="t-device",
                    state=state,
                    updated_at="2026-09-02T00:00:00Z",
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(update, state) for state in ("active", "complete")]
            outcomes = []
            for future in futures:
                try:
                    outcomes.append(future.result())
                except views.ProjectModelError as exc:
                    outcomes.append(str(exc))
            self.assertEqual(sum(item.startswith("sha256:") for item in outcomes), 1)
            self.assertEqual(outcomes.count("project brief digest conflict"), 1)

    def test_parser_and_edit_fail_closed_on_ambiguous_or_uncontrolled_input(self):
        text = markdown_fixture(REAL_PROJECT_FIXTURES["SWARM"])
        with self.assertRaisesRegex(views.ProjectModelError, "exactly one JSON"):
            views.parse_project_brief_markdown(text + "```json\n{}\n```\n")
        with self.assertRaisesRegex(views.ProjectModelError, "another project"):
            views.parse_project_brief_markdown(text, project_id="nemo")
        invalid = copy.deepcopy(REAL_PROJECT_FIXTURES["SWARM"])
        invalid["proposed_lens_ids"] = ["lens-overview", "LENS-OVERVIEW"]
        with self.assertRaisesRegex(views.ProjectModelError, "proposed_lens_ids"):
            views.parse_project_brief_markdown(markdown_fixture(invalid))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SWARM.md"
            path.write_text(text, encoding="utf-8")
            _, digest = views.parse_project_brief_markdown(text)
            before = path.read_bytes()
            with self.assertRaisesRegex(views.ProjectModelError, "not editable"):
                views.update_project_brief(
                    path,
                    expected_digest=digest,
                    collection="ownership",
                    record_id="owner",
                    state="changed",
                    updated_at="2026-09-02T00:00:00Z",
                )
            self.assertEqual(path.read_bytes(), before)

    def test_plugin_module_is_exact_mirror(self):
        plugin = CONSOLE_ROOT.parent / "plugins" / "swarm" / "console" / "project_model_views.py"
        self.assertEqual((CONSOLE_ROOT / "project_model_views.py").read_bytes(), plugin.read_bytes())


class FlowDefinitionTests(unittest.TestCase):
    def definition(self, identity="create", version=1):
        nodes = []
        for index, name in enumerate(("brief", "approach", "produce", "check", "accept")):
            previous = nodes[-1]["id"] if nodes else None
            nodes.append({
                "id": name, "objective": f"SWARM {name}", "owner_id": "owner-" + name,
                "capability": name, "dependencies": [previous] if previous else [],
                "inputs": [{"node_id": previous, "output_id": "result"}] if previous else [],
                "outputs": ["result"], "completion": "Return the bound artifact and required proof",
                "proof_classes": ["HUMAN" if name == "accept" else "SOURCE_STATIC"],
            })
        return self.seal({"id": identity, "version": version, "objective": "Create a bounded SWARM increment", "nodes": nodes})

    def seal(self, definition):
        definition["digest"] = "sha256:" + views._digest({key: value for key, value in definition.items() if key != "digest"})
        return definition

    def test_valid_definition_is_detached_and_not_acceptance(self):
        definition = self.definition()
        result = views.validate_flow_definition(definition)
        result["nodes"][0]["objective"] = "edited draft"
        self.assertNotEqual(result, definition)
        self.assertNotIn("accepted", definition)
        self.assertNotIn("run", definition)

    def test_invalid_graph_and_unknown_proof_are_rejected(self):
        mutations = (
            lambda d: d["nodes"].append(copy.deepcopy(d["nodes"][0])),
            lambda d: d["nodes"][0].update(dependencies=["accept"]),
            lambda d: d["nodes"][1].update(dependencies=["missing"]),
            lambda d: d["nodes"][1].update(inputs=[{"node_id": "accept", "output_id": "result"}]),
            lambda d: d["nodes"][1].update(inputs=[{"node_id": "brief", "output_id": "missing"}]),
            lambda d: d["nodes"][0].update(owner_id=""),
            lambda d: d["nodes"][0].update(proof_classes=["MODEL_SAYS_HUMAN_APPROVED"]),
            lambda d: d["nodes"][0].update(accepted=True),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                definition = self.definition()
                mutate(definition)
                with self.assertRaises(views.ProjectModelError):
                    views.validate_flow_definition(self.seal(definition))

    def test_tampered_pinned_bytes_fail_on_reload(self):
        definition = self.definition()
        definition["nodes"][0]["objective"] = "mutated after pin"
        with self.assertRaisesRegex(views.ProjectModelError, "digest mismatch"):
            views.parse_project_brief_markdown(markdown_fixture(project_fixture("swarm", flow_definitions=[definition])))

    def test_versions_append_through_existing_writer_and_keep_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SWARM.md"
            path.write_text(markdown_fixture(project_fixture("swarm")), encoding="utf-8")
            first = self.definition()
            _, digest = views.parse_project_brief_markdown(path.read_text(encoding="utf-8"))

            def append(definition, expected):
                return views.mutate_project_brief(path, expected_digest=expected, operation="create", collection="flow_definitions",
                    record_id=definition["id"], changes={key: value for key, value in definition.items() if key != "id"}, updated_at="2026-10-08T00:00:00Z")

            next_digest = append(first, digest)
            with self.assertRaisesRegex(views.ProjectModelError, "digest conflict"):
                append(self.definition(version=2), digest)
            with self.assertRaisesRegex(views.ProjectModelError, "last retained"):
                append(first, next_digest)
            second = self.definition(version=2)
            second["nodes"][0]["objective"] = "Revised brief"
            next_digest = append(self.seal(second), next_digest)
            next_digest = append(self.definition(identity="create-copy"), next_digest)
            restarted, actual_digest = views.parse_project_brief_markdown(path.read_text(encoding="utf-8"))
            self.assertEqual(actual_digest, next_digest)
            self.assertEqual(restarted["flow_definitions"][0], first)
            self.assertEqual([(item["id"], item["version"]) for item in restarted["flow_definitions"]], [("create", 1), ("create", 2), ("create-copy", 1)])
            with self.assertRaisesRegex(views.ProjectModelError, "append-only"):
                views.mutate_project_brief(path, expected_digest=next_digest, operation="update", collection="flow_definitions", record_id="create", changes={"objective": "rewrite"}, updated_at="today")

    def test_api_saved_versions_preview_and_restart_use_real_brief_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "SWARM.md"
            path.write_text(markdown_fixture(project_fixture("swarm")), encoding="utf-8")
            agents = [{"id": "owner-brief", "project_id": "swarm", "archived": False}]
            def app():
                return SimpleNamespace(_canonical_project_root=lambda *args: root,
                    _canonical_project_identities=lambda project: frozenset({project}),
                    _observed_scope=lambda **kwargs: ({}, agents, {}, {}))
            def call(payload):
                return server.App.project_flow_command(app(), {"project_id": "swarm", **payload})
            original = call({"operation": "read"})
            self.assertEqual(original["definitions"], [])
            definition = self.definition()
            definition["nodes"][0]["objective"] = "  Frame the cafe\u0301 outcome\nKeep the bound scope  "
            definition["nodes"][0]["completion"] = "  Return the artifact\nInclude its proof\tand identity  "
            self.seal(definition)
            draft = {key: value for key, value in definition.items() if key != "digest"}
            save = {"operation": "save", "expected_digest": original["source_digest"], "definition": draft, "acknowledge": True}
            with self.assertRaises(server.ConsoleError):
                call({**save, "acknowledge": False})
            saved = call(save)
            self.assertEqual(saved["definitions"], [definition])
            self.assertEqual(call({"operation": "read"})["definitions"], [definition])
            request = {"operation": "preview", "expected_digest": saved["source_digest"], "flow_id": "create", "version": 1, "flow_digest": definition["digest"]}
            preview = call(request)["preview"]
            self.assertEqual(preview["readiness"], "READY")
            self.assertEqual(preview["node_id"], "brief")
            self.assertFalse(preview["dispatch_available"])
            self.assertEqual(preview["waiting_node_ids"], ["approach", "produce", "check", "accept"])
            self.assertEqual(preview["task_manifest_draft"]["task_id"], "draft-only")
            self.assertEqual(preview["task_manifest_draft"]["task_name"], "Frame the café outcome Keep the bound scope")
            self.assertEqual(preview["task_manifest_draft"]["milestones"][0]["title"], "Frame the café outcome Keep the bound scope")
            self.assertEqual(preview["task_manifest_draft"]["blocks"][0]["title"], "Return the artifact Include its proof and identity")
            self.assertIn(definition["nodes"][0]["objective"], preview["instruction"])
            self.assertIn(definition["nodes"][0]["completion"], preview["instruction"])
            self.assertEqual(preview, call(request)["preview"])
            for field, value in (("flow_digest", "sha256:" + "a" * 64), ("expected_digest", original["source_digest"]), ("version", 2)):
                with self.subTest(field=field), self.assertRaises(server.ConsoleConflict):
                    call({**request, field: value})
            for forged in ({"accepted": True}, {"receipts": ["user approved", "deployed"]}, {"node_id": "accept"}):
                with self.assertRaises(server.ConsoleError):
                    call({**request, **forged})
            agents[0]["project_id"] = "another-project"
            self.assertEqual(call(request)["preview"]["readiness"], "WAITING")
            agents[0]["project_id"] = "swarm"
            agents[0]["id"] = "wrong-owner"
            self.assertEqual(call(request)["preview"]["readiness"], "WAITING")
            with self.assertRaises(server.ConsoleError):
                server.App.project_flow_command(app(), {"operation": "read", "project_id": "foreign"})
            next_draft = copy.deepcopy(draft)
            next_draft["version"] = 2
            next_draft["nodes"][0]["proof_classes"] = ["HUMAN"]
            current = call({**save, "expected_digest": saved["source_digest"], "definition": next_draft})
            with self.assertRaises(server.ConsoleConflict):
                call(request)
            pinned = call({**request, "expected_digest": current["source_digest"]})
            self.assertEqual(pinned["definitions"][0], definition)
            human_request = {**request, "expected_digest": current["source_digest"], "version": 2, "flow_digest": current["definitions"][-1]["digest"]}
            self.assertEqual(call(human_request)["preview"]["readiness"], "WAITING")


class ProjectTicketTests(unittest.TestCase):
    ACCEPTED_TASK = {"id": "t-accepted", "state": "accepted", "acceptance_receipt_ids": ["r-1"], "milestone_id": "m-flat"}

    def test_concurrent_create_replays_one_identity_and_stale_competitors_do_not_allocate(self):
        request = dict(operation="create", expected_digest=self.call({"operation": "read"})["source_digest"],
                       acknowledge=True, collection="goals", record_id="concurrent", changes={"label": "One"}, project_code="SWRM")
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.call(request), range(4)))
        self.assertEqual(sum(not r["replayed"] for r in results), 1)
        digest = results[0]["source_digest"]
        def competing(index):
            try:
                return self.call({**request, "expected_digest": digest, "record_id": f"next-{index}"})
            except server.ConsoleConflict:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(competing, range(4)))
        self.assertEqual(sum(r is not None for r in results), 1)
        identities = self.ticket_ledger.replay()["ticket_identities"]["swarm"]["assignments"]
        self.assertEqual(sorted(identities.values()), [1, 2])
        self.assertEqual(sum(r["id"] == "concurrent" for r in self.document()["objective"]["ranked_outcomes"]), 1)

    def test_ticket_allocation_uncertain_write_restart_and_exact_replay(self):
        from unittest import mock
        request = {"operation": "create", "collection": "goals", "record_id": "opaque-proof",
                   "changes": {"label": "Proof goal"}, "expected_digest": self.call({"operation": "read"})["source_digest"],
                   "acknowledge": True, "project_code": "swrm"}
        before = self.path.read_bytes()
        # Server imports its own module identity; patch the production writer actually called.
        module = sys.modules[server.mutate_project_tickets.__module__]
        with mock.patch.object(module, "_replace_brief_bytes", side_effect=OSError("simulated interrupted source write")):
            with self.assertRaisesRegex(server.ConsoleError, "SOURCE_WRITE_UNCERTAIN"):
                self.call(request)
        self.assertEqual(self.path.read_bytes(), before)
        retained = self.ticket_ledger._state.path.read_bytes()
        self.ticket_ledger = server.ProgressLedger(self.root / "ledger")
        result = self.call(request)
        self.assertEqual(self.by_id(result)["opaque-proof"]["display_id"], "SWRM-1")
        saved = self.path.read_bytes()
        self.assertTrue(self.call(request)["replayed"])
        self.assertEqual(self.path.read_bytes(), saved)
        self.assertEqual(self.ticket_ledger._state.path.read_bytes(), retained)
        document = self.document()
        next(r for r in document["objective"]["ranked_outcomes"] if r["id"] == "opaque-proof")["label"] = "Other author's edit"
        self.path.write_text(markdown_fixture(document), encoding="utf-8")
        edited = self.path.read_bytes()
        with self.assertRaises(server.ConsoleConflict):
            self.call(request)
        self.assertEqual(self.path.read_bytes(), edited)
        self.assertEqual(self.ticket_ledger._state.path.read_bytes(), retained)
        with self.assertRaises(server.ConsoleConflict):
            self.call({**request, "changes": {"label": "Different delivery"}})
        self.assertEqual(self.path.read_bytes(), edited)
        self.assertEqual(self.ticket_ledger._state.path.read_bytes(), retained)

    def test_missing_invalid_code_and_stale_source_do_not_allocate(self):
        digest = self.call({"operation": "read"})["source_digest"]
        request = dict(operation="create", expected_digest=digest, acknowledge=True,
                       collection="goals", record_id="new-goal", changes={"label": "Goal"})
        before = self.path.read_bytes()
        for extra, message in (({}, "PROJECT_CODE_REQUIRED"), ({"project_code": "TOOLONG"}, "PROJECT_CODE_INVALID"),
                               ({"project_code": None}, "PROJECT_CODE_INVALID"),
                               ({"project_code": "AA", "expected_digest": "sha256:" + "0" * 64}, "digest conflict")):
            with self.subTest(extra=extra), self.assertRaisesRegex(server.ConsoleError, message):
                self.call({**request, **extra})
            self.assertEqual(self.path.read_bytes(), before)
            self.assertFalse(self.ticket_ledger._state.path.exists())
        saved = self.call({**request, "project_code": "SWRM"})
        self.assertEqual(self.by_id(saved)["new-goal"]["display_id"], "SWRM-1")

    def test_old_and_new_mutators_require_digest_and_accepted_task_reparent_preserves_evidence(self):
        before = self.path.read_bytes()
        kwargs = dict(path=self.path, operation="update", collection="tasks", record_id="t-flat",
                      changes={"label": "Changed"}, updated_at="2026-10-25T00:00:00Z")
        with self.assertRaises(views.ProjectModelError):
            views.mutate_project_brief(expected_digest=None, **kwargs)
        with self.assertRaises(TypeError):
            views.mutate_project_brief(**kwargs)
        for digest in (None, ""):
            with self.assertRaises(server.ConsoleError):
                self.write(digest, "update", "tasks", "t-flat", {"label": "Changed"})
        self.assertEqual(self.path.read_bytes(), before)
        result = self.write(self.call({"operation": "read"})["source_digest"], "update", "tasks", "t-accepted", {"parent_id": None})
        self.assertEqual(self.by_id(result)["t-accepted"]["parent_status"], "ROOT")
        record = next(r for r in self.document()["tasks"] if r["id"] == "t-accepted")
        self.assertEqual(record, {k: v for k, v in self.ACCEPTED_TASK.items() if k != "milestone_id"})

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.ticket_ledger = server.ProgressLedger(self.root / "ledger")
        self.path = self.root / "SWARM.md"
        self.path.write_text(markdown_fixture(project_fixture(
            "swarm",
            objective={"current": "Advance swarm", "ranked_outcomes": [{"id": "g-legacy", "rank": 1, "milestone_id": "m-legacy", "note": "kept"}]},
            milestones=[{"id": "m-legacy", "state": "active", "task_ids": ["t-legacy"], "evidence_ids": ["e-1"]},
                        {"id": "m-flat", "state": "active"}],
            tasks=[{"id": "t-legacy", "state": "active", "custom": {"keep": True}},
                   {"id": "t-flat", "task_name": "Flat task"}, copy.deepcopy(self.ACCEPTED_TASK)],
            blocks=[{"id": "b-host", "task_id": "host-thread-1", "state": "accepted"}],
            artifacts=[{"id": "a-1", "revision": "abc", "proof_class": "SOURCE_STATIC"}],
        )), encoding="utf-8")

    def call(self, payload, project="swarm"):
        def binding(project_id, purpose="Project view"):
            return {"project_id": project_id, "root": self.root, "identities": frozenset({project_id}),
                    "identity_error": None, "native_id": None}
        app = SimpleNamespace(_canonical_project_root=lambda *args: self.root,
                              _canonical_project_identities=lambda project_id: frozenset({project_id}),
                              _saved_project_binding=binding, progress_ledger=self.ticket_ledger,
                              _bound_blocks_accepted=server.App._bound_blocks_accepted)
        # Real retained-execution projection against the real ledger; only root/identity observation is a fixture.
        app._retained_execution_tickets = lambda *args: server.App._retained_execution_tickets(app, *args)
        return server.App.project_ticket_command(app, {"project_id": project, **payload})

    def write(self, digest, operation, collection, record_id, changes):
        return self.call({**({"project_code": "SWRM"} if operation == "create" else {}),
                          "operation": operation, "expected_digest": digest, "acknowledge": True,
                          "collection": collection, "record_id": record_id, "changes": changes})

    @staticmethod
    def by_id(result):
        return {item["id"]: item for item in result["records"]}

    def document(self):
        return views.parse_project_brief_markdown(self.path.read_text(encoding="utf-8"))[0]

    def test_all_four_kinds_priority_assignment_reparent_and_restart(self):
        read = self.call({"operation": "read"})
        records = self.by_id(read)
        self.assertEqual(read["hierarchy"], ["goal", "milestone", "task", "block"])
        self.assertEqual((records["m-legacy"]["parent"], records["m-legacy"]["parent_status"]), ({"kind": "goal", "id": "g-legacy"}, "BOUND"))
        self.assertEqual(records["t-legacy"]["parent"], {"kind": "milestone", "id": "m-legacy"})
        self.assertEqual((records["t-flat"]["parent"], records["t-flat"]["parent_status"], records["t-flat"]["label"]), (None, "ROOT", "Flat task"))
        self.assertEqual(records["b-host"]["parent_status"], "DANGLING")  # External host task is never claimed.
        self.assertTrue(all("progress_percent" not in item and "accepted" not in item for item in read["records"]))
        result = self.write(read["source_digest"], "create", "goals", "g-ship", {"label": "Ship tickets", "priority": "high", "rank": 2})
        result = self.write(result["source_digest"], "create", "milestones", "m-ship", {"label": "Ticket API", "parent_id": "g-ship", "priority": "critical"})
        result = self.write(result["source_digest"], "create", "tasks", "t-ship",
                            {"label": "Implement", "parent_id": "m-ship", "assignment": {"assignee_id": "agent-7", "role_id": "developer"}})
        result = self.write(result["source_digest"], "create", "blocks", "b-ship", {"label": "Validator", "parent_id": "t-ship", "description": "Fail closed"})
        records = self.by_id(result)
        self.assertEqual([records[key]["kind"] for key in ("g-ship", "m-ship", "t-ship", "b-ship")], ["goal", "milestone", "task", "block"])
        self.assertEqual(records["m-ship"]["parent"], {"kind": "goal", "id": "g-ship"})
        self.assertEqual(records["b-ship"]["parent"], {"kind": "task", "id": "t-ship"})
        self.assertEqual(records["t-ship"]["assignment"], {"assignee_id": "agent-7", "role_id": "developer"})
        self.assertEqual((records["g-ship"]["priority"], records["g-ship"]["rank"], records["b-ship"]["description"]), ("high", 2, "Fail closed"))
        self.assertEqual(records["b-ship"]["declared_state"], "planned")  # Planning only, never execution credit.
        self.assertTrue(all(records[key]["declared_state"] == "planned" for key in ("g-ship", "m-ship", "t-ship", "b-ship")))
        self.assertIsNone(records["t-flat"]["declared_state"])  # Historical absence stays unknown.
        self.assertEqual(self.document()["objective"]["ranked_outcomes"][-1], {"id": "g-ship", "state": "planned", "label": "Ship tickets", "priority": "high", "rank": 2})

        result = self.write(result["source_digest"], "update", "tasks", "t-legacy", {"parent_id": "m-ship", "priority": "low", "label": "Moved"})
        milestones = {item["id"]: item for item in self.document()["milestones"]}
        moved = next(item for item in self.document()["tasks"] if item["id"] == "t-legacy")
        self.assertEqual((milestones["m-legacy"]["task_ids"], milestones["m-legacy"]["evidence_ids"]), ([], ["e-1"]))
        self.assertEqual((moved["milestone_id"], moved["state"], moved["custom"], moved["label"]), ("m-ship", "active", {"keep": True}, "Moved"))
        result = self.write(result["source_digest"], "update", "tasks", "t-flat", {"parent_id": "m-flat", "rank": 5})
        self.assertEqual(self.by_id(result)["t-flat"]["parent"], {"kind": "milestone", "id": "m-flat"})
        result = self.write(result["source_digest"], "update", "tasks", "t-flat", {"parent_id": None, "rank": None, "assignment": {"assignee_id": "agent-8"}})
        result = self.write(result["source_digest"], "update", "tasks", "t-flat", {"assignment": None})
        self.assertEqual((self.by_id(result)["t-flat"]["parent_status"], self.by_id(result)["t-flat"]["rank"], self.by_id(result)["t-flat"]["assignment"]), ("ROOT", None, None))
        result = self.write(result["source_digest"], "update", "tasks", "t-accepted", {"label": "Retained label"})
        result = self.write(result["source_digest"], "update", "blocks", "b-host", {"priority": "medium"})
        document = self.document()
        self.assertEqual(next(item for item in document["tasks"] if item["id"] == "t-accepted"), {**self.ACCEPTED_TASK, "label": "Retained label"})
        self.assertEqual(next(item for item in document["blocks"] if item["id"] == "b-host"),
                         {"id": "b-host", "task_id": "host-thread-1", "state": "accepted", "priority": "medium"})
        self.assertEqual(document["objective"]["ranked_outcomes"][0], {"id": "g-legacy", "rank": 1, "milestone_id": "m-legacy", "note": "kept"})
        self.assertEqual(document["milestones"][1], {"id": "m-flat", "state": "active"})
        restarted = self.call({"operation": "read"})
        self.assertEqual((restarted["source_digest"], restarted["records"]), (result["source_digest"], result["records"]))

    def test_invalid_stale_cross_project_and_ambiguous_edits_write_nothing(self):
        digest = self.call({"operation": "read"})["source_digest"]
        digest = self.write(digest, "create", "blocks", "b-new", {"label": "New block", "parent_id": "t-flat"})["source_digest"]
        before = self.path.read_bytes()
        rejected = (
            ("create", "tasks", "T-LEGACY", {"label": "Duplicate"}),
            ("create", "tasks", "a-1", {"label": "Duplicates an artifact"}),
            ("create", "tasks", "t-unlabelled", {"priority": "high"}),
            ("create", "risks_blockers", "r-new", {"label": "Not a ticket"}),
            ("create", "flow_definitions", "flow", {"label": "Not a ticket"}),
            ("create", "tasks", "", {"label": "Empty id"}),
            ("create", "tasks", "bad\x00id", {"label": "Control id"}),
            ("update", "tasks", "t-missing", {"label": "Missing"}),
            ("update", "tasks", "b-new", {"label": "Wrong collection"}),
            ("update", "tasks", "t-flat", {}),
            ("update", "tasks", "t-flat", {"state": "complete"}),
            ("update", "tasks", "t-flat", {"progress_percent": 50}),
            ("update", "tasks", "t-flat", {"owner_id": "agent-1"}),
            ("update", "tasks", "t-flat", {"acceptance_receipt": "forged"}),
            ("update", "tasks", "t-flat", {"label": "Done", "completed": True}),
            ("update", "tasks", "t-flat", {"id": "renamed"}),
            ("update", "tasks", "t-flat", {"priority": "urgent"}),
            ("update", "tasks", "t-flat", {"rank": -1}),
            ("update", "tasks", "t-flat", {"rank": True}),
            ("update", "tasks", "t-flat", {"rank": 1.5}),
            ("update", "tasks", "t-flat", {"label": ""}),
            ("update", "tasks", "t-flat", {"label": None}),
            ("update", "tasks", "t-flat", {"label": "two\nlines"}),
            ("update", "tasks", "t-flat", {"description": "x" * 4097}),
            ("update", "tasks", "t-flat", {"assignment": {}}),
            ("update", "tasks", "t-flat", {"assignment": {"assignee_id": "bad id!"}}),
            ("update", "tasks", "t-flat", {"assignment": {"executor": "agent-1"}}),
            ("update", "tasks", "t-flat", {"parent_id": "t-flat"}),  # self
            ("update", "tasks", "t-flat", {"parent_id": "m-missing"}),  # dangling
            ("update", "tasks", "t-flat", {"parent_id": "g-legacy"}),  # wrong kind
            ("update", "tasks", "t-flat", {"parent_id": " m-flat"}),
            ("update", "goals", "g-legacy", {"parent_id": "m-flat"}),  # goals are roots
            ("update", "milestones", "m-flat", {"parent_id": "t-flat"}),  # cycle attempt
            ("update", "blocks", "b-new", {"parent_id": None}),  # blocks remain under tasks
            ("update", "blocks", "b-new", {"parent_id": "b-host"}),  # deep nesting
            ("update", "blocks", "b-new", {"parent_id": "m-flat"}),
            ("update", "milestones", "m-legacy", {"parent_id": None}),  # legacy goal association
            ("update", "blocks", "b-host", {"parent_id": "t-flat"}),  # external host parent retained
        )
        for operation, collection, record_id, changes in rejected:
            with self.subTest(operation=operation, record_id=record_id, changes=changes):
                with self.assertRaises(server.ConsoleError):
                    self.write(digest, operation, collection, record_id, changes)
                self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(server.ConsoleConflict):
            self.write("sha256:" + "0" * 64, "update", "tasks", "t-flat", {"label": "Stale"})
        base = {"operation": "update", "expected_digest": digest, "acknowledge": True, "collection": "tasks",
                "record_id": "t-flat", "changes": {"label": "Changed"}}
        for payload in ({**base, "acknowledge": False}, {**base, "approved": True}, {**base, "operation": "delete"},
                        {**base, "expected_digest": "latest"}, {"operation": "read", "expected_digest": digest}):
            with self.subTest(payload=payload), self.assertRaises(server.ConsoleError):
                self.call(payload)
        with self.assertRaises(server.ConsoleError):
            self.call({"operation": "read"}, project="foreign")
        with self.assertRaises(server.ConsoleError):
            self.call(base, project="foreign")
        self.assertEqual(self.path.read_bytes(), before)

    def test_migrate_legacy_types_strings_once_with_exact_history_and_cas(self):
        document = self.document()
        long_text = "Second line\nkept verbatim " + "x" * 170
        document["milestones"] = ["Ship the legacy milestone", long_text, *document["milestones"]]
        document["objective"]["ranked_outcomes"].append("Legacy outcome text")
        self.path.write_text(markdown_fixture(document), encoding="utf-8")
        original = self.path.read_bytes()
        _, digest = views.parse_project_brief_markdown(original.decode("utf-8"))
        with self.assertRaises(server.ConsoleError):
            self.call({"operation": "read"})  # Legacy strings are not typed tickets; reads never migrate.
        base = {"operation": "migrate_legacy", "expected_digest": digest, "acknowledge": True}
        for payload in ({**base, "acknowledge": False}, {**base, "collection": "milestones"}, {**base, "expected_digest": "latest"},
                        {key: value for key, value in base.items() if key != "expected_digest"}):
            with self.subTest(payload=payload), self.assertRaises(server.ConsoleError):
                self.call(payload)
        with self.assertRaises(server.ConsoleConflict):
            self.call({**base, "expected_digest": "sha256:" + "0" * 64})
        with self.assertRaises(server.ConsoleError):
            self.call(base, project="foreign")
        with self.assertRaises(views.ProjectModelError):
            views.migrate_legacy_project_tickets(self.path, expected_digest=None, updated_at="2026-10-25T00:00:00Z", project_ids={"swarm"})
        with self.assertRaisesRegex(views.ProjectModelError, "timestamp"):
            views.migrate_legacy_project_tickets(self.path, expected_digest=digest, updated_at="  ", project_ids={"swarm"})
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse((self.root / "history").exists())
        result = self.call(base)
        self.assertEqual(result["migration"]["counts"], {"milestones": 2, "ranked_outcomes": 1})
        self.assertEqual((result["previous_digest"], result["replayed"]), (digest, False))
        history = result["migration"]["history"]
        self.assertEqual((history["rel"], history["sha256"], history["bytes"], history["canonical_digest"], history["project_id"]),
                         ("brief_content", hashlib.sha256(original).hexdigest(), len(original), digest, "swarm"))
        self.assertEqual(views.read_brief_content(self.root, history), original)
        migrated = self.document()
        first, second = migrated["milestones"][:2]
        self.assertEqual(first, {"id": first["id"], "label": "Ship the legacy milestone"})
        self.assertEqual(second, {"id": second["id"], "description": long_text})
        goal = migrated["objective"]["ranked_outcomes"][-1]
        self.assertEqual(goal, {"id": goal["id"], "label": "Legacy outcome text"})
        self.assertEqual(result["migration"]["converted_ids"], sorted([first["id"], second["id"], goal["id"]]))
        self.assertEqual(first["id"], views._legacy_ticket_record("milestone", "Ship the legacy milestone")["id"])
        self.assertEqual(migrated["milestones"][2:], document["milestones"][2:])
        self.assertEqual(migrated["objective"]["ranked_outcomes"][:-1], document["objective"]["ranked_outcomes"][:-1])
        self.assertEqual({key: value for key, value in migrated.items() if key not in {"milestones", "objective", "updated_at"}},
                         {key: value for key, value in document.items() if key not in {"milestones", "objective", "updated_at"}})
        records = self.by_id(result)
        self.assertEqual((records[first["id"]]["kind"], records[first["id"]]["label"], records[goal["id"]]["kind"]),
                         ("milestone", "Ship the legacy milestone", "goal"))
        self.assertEqual((records[second["id"]]["label"], records[second["id"]]["description"]), (second["id"], long_text))
        self.assertTrue(all(records[item]["declared_state"] is None and records[item]["display_id"] is None
                            for item in result["migration"]["converted_ids"]))
        self.assertEqual(records["t-accepted"]["declared_state"], "accepted")  # Typed records keep their exact state.
        saved = self.path.read_bytes()
        with self.assertRaises(server.ConsoleConflict):
            self.call(base)  # A stale digest after migration is a CAS conflict, never a second write.
        again = self.call({**base, "expected_digest": result["source_digest"]})
        self.assertEqual((again["source_digest"], again["migration"]["counts"], again["migration"]["history"]),
                         (result["source_digest"], {"milestones": 0, "ranked_outcomes": 0}, None))
        self.assertEqual(self.path.read_bytes(), saved)
        self.assertEqual([item.name for item in (self.root / "history").iterdir()], [Path(history["path"]).name])
        restarted = load_module("restarted_migration_views", CONSOLE_ROOT / "project_model_views.py")
        observed, observed_digest = restarted.parse_project_brief_markdown(saved.decode("utf-8"))
        self.assertEqual((observed, observed_digest), (migrated, result["source_digest"]))
        read = self.call({"operation": "read"})
        self.assertEqual((read["source_digest"], read["records"]), (result["source_digest"], result["records"]))
        self.assertFalse(self.ticket_ledger._state.path.exists())

    def test_migrate_legacy_rejects_collisions_malformed_entries_and_hostile_history_without_writing(self):
        collide = views._legacy_ticket_record("milestone", "Collides")["id"]
        cases = (
            {"milestones": ["Same text", "Same text"]},
            {"milestones": ["Fine", 7]},
            {"milestones": ["   "]},
            {"milestones": ["bad\x00text"]},
            {"milestones": ["x" * 4097]},
            {"objective": {"current": "Advance swarm", "ranked_outcomes": ["Dup", "Dup"]}},
            {"objective": {"current": "Advance swarm", "ranked_outcomes": [None]}},
            {"milestones": ["Collides"], "tasks": [{"id": collide, "state": "planned"}]},
            {"milestones": ["Collides"], "artifacts": [{"id": collide.upper(), "revision": "abc", "proof_class": "SOURCE_STATIC"}]},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                self.path.write_text(markdown_fixture({**self.document(), **changes}), encoding="utf-8")
                before = self.path.read_bytes()
                _, digest = views.parse_project_brief_markdown(before.decode("utf-8"))
                with self.assertRaises(server.ConsoleError):
                    self.call({"operation": "migrate_legacy", "expected_digest": digest, "acknowledge": True})
                self.assertEqual(self.path.read_bytes(), before)
                self.assertFalse((self.root / "history").exists())
        document = self.document()
        document["milestones"] = ["Retained verbatim", *document["milestones"]]
        self.path.write_text(markdown_fixture(document), encoding="utf-8")
        before = self.path.read_bytes()
        _, digest = views.parse_project_brief_markdown(before.decode("utf-8"))
        request = {"operation": "migrate_legacy", "expected_digest": digest, "acknowledge": True}
        archive = self.root / "history" / f"swarm-brief-{hashlib.sha256(before).hexdigest()}.md"
        archive.parent.mkdir()
        decoy = self.root / "decoy.md"
        decoy.write_bytes(before)  # Same bytes behind a link must still be refused as retained history.
        try:
            os.symlink(decoy, archive)
            linked = True
        except (OSError, NotImplementedError):
            linked = False
        if linked:
            with self.subTest(hostile="symlink"), self.assertRaises(server.ConsoleError):
                self.call(request)
            self.assertEqual(self.path.read_bytes(), before)
            self.assertTrue(archive.is_symlink())
            archive.unlink()
        archive.write_bytes(b"pre-existing conflicting archive")
        with self.subTest(hostile="conflict"), self.assertRaises(server.ConsoleError):
            self.call(request)
        self.assertEqual((self.path.read_bytes(), archive.read_bytes(), decoy.read_bytes()),
                         (before, b"pre-existing conflicting archive", before))
        self.assertFalse(self.ticket_ledger._state.path.exists())

    def test_conflicting_duplicate_absent_and_empty_briefs_fail_closed(self):
        document = self.document()
        document["tasks"][0]["milestone_id"] = "m-flat"  # also listed by m-legacy.task_ids
        self.path.write_text(markdown_fixture(document), encoding="utf-8")
        read = self.call({"operation": "read"})
        self.assertEqual(self.by_id(read)["t-legacy"]["parent_status"], "CONFLICT")
        before = self.path.read_bytes()
        for changes in ({"parent_id": "m-flat"}, {"parent_id": None}):
            with self.assertRaises(server.ConsoleError):
                self.write(read["source_digest"], "update", "tasks", "t-legacy", changes)
        with self.assertRaises(server.ConsoleError):
            self.write(read["source_digest"], "create", "blocks", "b-child", {"label": "Child", "parent_id": "t-legacy"})
        self.assertEqual(self.path.read_bytes(), before)
        self.write(read["source_digest"], "update", "tasks", "t-legacy", {"label": "Label edits keep legacy shape"})
        document = self.document()
        document["blocks"].append({"id": "T-FLAT"})
        self.path.write_text(markdown_fixture(document), encoding="utf-8")
        with self.assertRaisesRegex(server.ConsoleError, "duplicate stable id"):
            self.call({"operation": "read"})
        self.path.write_text("", encoding="utf-8")
        with self.assertRaises(server.ConsoleError):
            self.call({"operation": "read"})
        self.path.unlink()
        with self.assertRaises(server.ConsoleError):
            self.call({"operation": "read"})
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
