from __future__ import annotations

import copy
import concurrent.futures
import importlib.util
import json
import tempfile
import unittest
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
                state="active",
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


if __name__ == "__main__":
    unittest.main()
