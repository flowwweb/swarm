from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


CONSOLE_ROOT = Path(__file__).resolve().parents[1]
if str(CONSOLE_ROOT) not in sys.path:
    sys.path.insert(0, str(CONSOLE_ROOT))

import server as console  # noqa: E402
from skills_catalog import resolve  # noqa: E402


class SkillsAndEtaContractTests(unittest.TestCase):
    def test_catalog_is_fail_closed_and_matching_is_allowlisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = console.ConsoleStore(Path(directory) / "console.sqlite3")
            catalog = store.skill_catalog()
        self.assertIn("find-skills", {item["skill_id"] for item in catalog})
        result = resolve(catalog, None, None, None, role="CTRL", task_kind="DISCOVERY")
        by_id = {item["skill_id"]: item for item in result["skills"]}
        self.assertEqual(by_id["find-skills"]["status"], "blocked_unreviewed")
        self.assertEqual(by_id["swarm"]["status"], "inherited")
        self.assertFalse(any(item["status"] == "inherited" for item in result["skills"] if item["skill_id"] == "frontend-design"))

    def test_scope_overlay_is_optimistic_and_reset_reveals_global_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = console.ConsoleStore(Path(directory) / "console.sqlite3")
            overlay = store.update_skill_scope(
                "project", "project:alpha",
                {"inheritance_enabled": False, "profile": "debug", "preferred_ids": ["find-skills"]},
                expected_revision=0, now_ms=10,
            )
            self.assertEqual(overlay["revision"], 1)
            with self.assertRaises(console.ConsoleConflict):
                store.update_skill_scope(
                    "project", "project:alpha", {"inheritance_enabled": True},
                    expected_revision=0, now_ms=11,
                )
            self.assertTrue(store.reset_skill_scope("project", "project:alpha", expected_revision=1))
            self.assertIsNone(store.skill_scope("project", "project:alpha"))

    def test_app_skill_projection_validates_observed_ctrl_and_uses_overlay_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.toml"
            app = console.App(root, config, root / "console.sqlite3")
            overview = {
                "nodes": [{"id": "ctrl-1", "project_id": "project:alpha", "role": "ctrl", "status": "active"}],
                "links": [], "projects": [], "controllers": [],
            }
            with mock.patch.object(app, "_host_overview", return_value=overview):
                app.update_skill_settings("project", "project:alpha", {"profile": "design"}, 0)
                projection = app.skill_settings(project_id="project:alpha", role="DESIGNER", task_kind="DESIGN")
            self.assertEqual(projection["overlays"]["project"]["profile"], "design")
            self.assertEqual(projection["settings"]["profile"], "design")
            with self.assertRaises(console.ConsoleError):
                app.update_skill_settings("ctrl", "unknown", {"profile": "debug"}, 0)

    def test_eta_does_not_infer_from_elapsed_tokens_or_quiet_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = console.ConsoleStore(Path(directory) / "console.sqlite3")
            now = 1_000_000
            overview = {
                "heartbeat_minutes": 1,
                "nodes": [{"id": "task-1", "project_id": "project:alpha", "status": "quiet", "tokens": 999999, "created_at": now - 99 * 60 * 60 * 1000, "updated_at": now - 120_000}],
                "links": [],
            }
            store.observe_overview(overview, now_ms=now, trigger="startup", heartbeat_minutes=1)
            store.observe_overview(overview, now_ms=now + 1_000, trigger="heartbeat", heartbeat_minutes=1)
            self.assertEqual(store.latest_forecasts(), {})
            connection = sqlite3.connect(Path(directory) / "console.sqlite3")
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM task_heartbeats").fetchone()[0], 1)
            finally:
                connection.close()

    def test_task_owner_eta_report_appends_revision_and_preserves_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = console.ConsoleStore(Path(directory) / "console.sqlite3")
            now = 1_000_000
            basis = {"milestones": [{"id": "build", "state": "in_progress"}]}
            first_receipt = {
                "receipt_type": "swarm_task_owner_forecast", "source": "owner:task-1", "receipt": "r1",
                "task_id": "task-1", "project_id": "project:alpha", "reason_code": "scope_discovered",
                "short_reason": "Owner accepted the initial estimate.",
                "baseline": {"eta_start_ms": now + 60_000, "eta_end_ms": now + 360_000, "confidence": 70},
                "current": {"eta_start_ms": now + 60_000, "eta_end_ms": now + 360_000, "confidence": 70, "status": "in_progress", "progress_basis": basis},
            }
            store.observe_overview({"nodes": [{"id": "task-1", "project_id": "project:alpha", "status": "active", "eta_report": first_receipt}], "links": []}, now_ms=now, trigger="startup", heartbeat_minutes=30)
            first = store.latest_forecasts()["task-1"]
            second_receipt = {**first_receipt, "receipt": "r2", "reason_code": "dependency", "short_reason": "Dependency moved the owner forecast.", "current": {**first_receipt["current"], "eta_end_ms": now + 600_000, "confidence": 45, "status": "blocked"}}
            store.observe_overview({"nodes": [{"id": "task-1", "project_id": "project:alpha", "status": "active", "eta_report": second_receipt}], "links": []}, now_ms=now + 60_000, trigger="state_change", heartbeat_minutes=30)
            current = store.latest_forecasts()["task-1"]
            self.assertEqual(first["revision"], 1)
            self.assertEqual(current["revision"], 2)
            self.assertEqual(current["baseline_eta_end_ms"], first["baseline_eta_end_ms"])
            self.assertEqual(current["delta_from_baseline_ms"], 240_000)
            self.assertEqual(current["reason_code"], "dependency")
            self.assertEqual(current["previous"]["eta_end_ms"], first["current"]["eta_end_ms"])
            self.assertEqual(current["current"]["status"], "blocked")

    def test_subagent_eta_receipt_rolls_into_master_without_double_counting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = console.ConsoleStore(Path(directory) / "console.sqlite3")
            receipt = {
                "receipt_type": "swarm_task_owner_forecast", "source": "owner:master", "receipt": "master-r1",
                "task_id": "master", "project_id": "project:alpha", "reason_code": "material_progress",
                "short_reason": "Master milestone accepted.",
                "baseline": {"eta_start_ms": 10, "eta_end_ms": 100, "confidence": 80},
                "current": {"eta_start_ms": 10, "eta_end_ms": 100, "confidence": 80, "status": "in_progress", "progress_basis": {"milestones": [{"id": "one"}]}},
            }
            store.observe_overview({"nodes": [
                {"id": "master", "project_id": "project:alpha", "status": "active", "eta_report": receipt},
                {"id": "sub", "project_id": "project:alpha", "status": "active", "is_subagent": True, "eta_report": {**receipt, "task_id": "sub", "receipt": "sub-r1"}},
            ], "links": []}, now_ms=1, trigger="startup", heartbeat_minutes=30)
            self.assertEqual(set(store.latest_forecasts()), {"master"})

    def test_eta_reports_reject_caller_authority_unknown_scope_duplicate_and_baseline_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = console.ConsoleStore(Path(directory) / "console.sqlite3")
            base = {
                "receipt_type": "swarm_task_owner_forecast", "source": "owner:task", "receipt": "r1",
                "task_id": "task", "project_id": "project:alpha", "reason_code": "material_progress",
                "short_reason": "Owner report.",
                "baseline": {"eta_start_ms": 10, "eta_end_ms": 100, "confidence": 80},
                "current": {"eta_start_ms": 10, "eta_end_ms": 100, "confidence": 80, "status": "in_progress", "progress_basis": {"milestones": [{"id": "one"}]}},
            }
            caller_claim = {**base, "authority": "task_owner"}
            unknown = {**base, "task_id": "other"}
            for report in (caller_claim, unknown):
                store.observe_overview({"nodes": [{"id": "task", "project_id": "project:alpha", "eta_report": report}], "links": []}, now_ms=1, trigger="startup", heartbeat_minutes=30)
            self.assertEqual(store.latest_forecasts(), {})
            store.observe_overview({"nodes": [{"id": "task", "project_id": "project:alpha", "eta_report": base}], "links": []}, now_ms=2, trigger="startup", heartbeat_minutes=30)
            store.observe_overview({"nodes": [{"id": "task", "project_id": "project:alpha", "eta_report": base}], "links": []}, now_ms=3, trigger="heartbeat", heartbeat_minutes=30)
            self.assertEqual(store.latest_forecasts()["task"]["revision"], 1)
            conflict = {**base, "receipt": "r2", "baseline": {**base["baseline"], "eta_end_ms": 200}}
            with self.assertRaisesRegex(console.ConsoleError, "baseline conflicts"):
                store.observe_overview({"nodes": [{"id": "task", "project_id": "project:alpha", "eta_report": conflict}], "links": []}, now_ms=4, trigger="state_change", heartbeat_minutes=30)


if __name__ == "__main__":
    unittest.main()
