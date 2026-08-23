from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock


CONSOLE_ROOT = Path(__file__).resolve().parents[1]
if str(CONSOLE_ROOT) not in sys.path:
    sys.path.insert(0, str(CONSOLE_ROOT))

import server as console  # noqa: E402
from runtime.progress_events import write_progress_pulse  # noqa: E402


class ConsoleProgressPulseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.codex_home = self.root / "codex"
        self.codex_home.mkdir()
        self.store = console.ConsoleStore(self.root / "console.sqlite3")
        self.overview = {
            "nodes": [{"id": "task-1", "project_id": "project:alpha", "virtual": False, "is_subagent": False}],
            "links": [],
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def pulse(
        *,
        observed_at_ms: int,
        pulse_receipt: str,
        completed_units: int | None = None,
        receipt_id: str = "material-1",
        project_id: str = "project:alpha",
        task_id: str = "task-1",
        plan_id: str = "plan-alpha",
        previous_plan_id: str | None = None,
        total_units: int = 4,
    ) -> dict:
        progress = None
        if completed_units is not None:
            progress = {
                "receipt_id": receipt_id,
                "plan_id": plan_id,
                "previous_plan_id": previous_plan_id,
                "unit_id": "unit-build",
                "unit_kind": "milestone",
                "total_units": total_units,
                "completed_units": completed_units,
                "basis": "Accepted milestones",
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

    def ingest(self, payload: dict, *, now_ms: int) -> dict:
        write_progress_pulse(self.codex_home, payload)
        return self.store.ingest_progress_pulses(self.codex_home, self.overview, now_ms=now_ms)

    def test_material_progress_advances_but_ordinary_heartbeat_does_not(self) -> None:
        first = self.ingest(self.pulse(observed_at_ms=10, pulse_receipt="pulse-1", completed_units=1), now_ms=10)
        self.assertEqual(first["advanced"], 1)
        self.assertEqual(self.store.latest_progress()["task-1"]["progress_basis"]["plan_units"]["completed_units"], 1)
        heartbeat = self.ingest(self.pulse(observed_at_ms=20, pulse_receipt="pulse-2"), now_ms=20)
        self.assertEqual(heartbeat["heartbeats"], 1)
        self.assertEqual(self.store.latest_progress()["task-1"]["progress_basis"]["plan_units"]["completed_units"], 1)

    def test_duplicate_is_idempotent_and_conflict_or_regression_is_rejected(self) -> None:
        original = self.pulse(observed_at_ms=10, pulse_receipt="pulse-1", completed_units=2)
        self.assertEqual(self.ingest(original, now_ms=10)["advanced"], 1)
        self.assertEqual(self.ingest(original, now_ms=20)["duplicates"], 1)
        regression = self.pulse(observed_at_ms=30, pulse_receipt="pulse-3", completed_units=1, receipt_id="material-2")
        self.assertEqual(self.ingest(regression, now_ms=30)["rejected"], 1)
        conflict = self.pulse(observed_at_ms=40, pulse_receipt="pulse-4", completed_units=3, receipt_id="material-3", total_units=5)
        self.assertEqual(self.ingest(conflict, now_ms=40)["rejected"], 1)
        self.assertEqual(self.store.latest_progress()["task-1"]["progress_basis"]["plan_units"]["completed_units"], 2)
        with closing(sqlite3.connect(self.root / "console.sqlite3")) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM task_progress_receipts").fetchone()[0], 1)

    def test_plan_change_requires_explicit_revision_and_wrong_target_fails_closed(self) -> None:
        self.assertEqual(self.ingest(self.pulse(observed_at_ms=10, pulse_receipt="pulse-1", completed_units=2), now_ms=10)["advanced"], 1)
        implicit = self.pulse(observed_at_ms=20, pulse_receipt="pulse-2", completed_units=1, receipt_id="material-2", plan_id="plan-beta")
        self.assertEqual(self.ingest(implicit, now_ms=20)["rejected"], 1)
        explicit = self.pulse(observed_at_ms=30, pulse_receipt="pulse-3", completed_units=1, receipt_id="material-3", plan_id="plan-beta", previous_plan_id="plan-alpha")
        self.assertEqual(self.ingest(explicit, now_ms=30)["advanced"], 1)
        wrong = self.pulse(observed_at_ms=40, pulse_receipt="pulse-4", task_id="other-task")
        self.assertEqual(self.ingest(wrong, now_ms=40)["rejected"], 1)
        self.assertEqual(self.store.latest_progress()["task-1"]["progress_basis"]["plan_units"]["plan_id"], "plan-beta")

    def test_material_receipt_history_is_bounded_while_latest_state_advances(self) -> None:
        with mock.patch.object(console, "PROGRESS_RECEIPTS_PER_TASK", 2):
            for completed in (1, 2, 3):
                result = self.ingest(
                    self.pulse(
                        observed_at_ms=completed * 10,
                        pulse_receipt=f"pulse-{completed}",
                        receipt_id=f"material-{completed}",
                        completed_units=completed,
                    ),
                    now_ms=completed * 10,
                )
                self.assertEqual(result["advanced"], 1)
        with closing(sqlite3.connect(self.root / "console.sqlite3")) as connection:
            rows = connection.execute(
                "SELECT receipt_id FROM task_progress_receipts ORDER BY observed_at_ms"
            ).fetchall()
        self.assertEqual(rows, [("material-2",), ("material-3",)])
        self.assertEqual(
            self.store.latest_progress()["task-1"]["progress_basis"]["plan_units"]["completed_units"],
            3,
        )

    def test_eta_report_is_bound_to_observed_target_and_progress_stays_separate(self) -> None:
        payload = self.pulse(observed_at_ms=10, pulse_receipt="pulse-1")
        payload["eta_report"] = {
            "receipt_type": "swarm_task_owner_forecast",
            "source": "task_owner:local",
            "receipt": "eta-1",
            "task_id": "task-1",
            "project_id": "project:alpha",
            "reason_code": "state_change",
            "short_reason": "Owner refreshed the forecast.",
            "baseline": {"eta_start_ms": 20, "eta_end_ms": 40, "confidence": 70},
            "current": {"eta_start_ms": 20, "eta_end_ms": 40, "confidence": 70, "status": "in_progress", "progress_basis": {"receipts": ["eta-1"]}},
        }
        result = self.ingest(payload, now_ms=10)
        self.assertEqual(result["eta_reports"]["task-1"]["receipt"], "eta-1")
        self.assertEqual(self.store.latest_forecasts()["task-1"]["revision"], 1)
        self.assertEqual(self.store.latest_progress(), {})

    def test_mixed_fresh_and_stale_units_use_oldest_coverage_observation(self) -> None:
        def node(task_id: str, observed_at_ms: int) -> dict:
            return {
                "id": task_id,
                "project_id": "project:alpha",
                "role": "doer",
                "status": "active",
                "virtual": False,
                "is_subagent": False,
                "eta": {
                    "trigger": "task_owner_report",
                    "receipt_source": "instruction_only_local_sidecar:task_owner:local",
                    "progress_source": "instruction_only_local_sidecar",
                    "progress_basis": {
                        "receipts": [f"material-{task_id}"],
                        "plan_units": {
                            "plan_id": "plan-alpha",
                            "unit_id": f"unit-{task_id}",
                            "unit_kind": "milestone",
                            "total_units": 2,
                            "completed_units": 1,
                            "basis": "Accepted milestones",
                            "observed_at_ms": observed_at_ms,
                        },
                    },
                },
                "proof_snapshot": {"media": []},
            }

        summary = console.App._progress_for_nodes(
            [node("old", 1_000), node("fresh", 9_000)],
            {"type": "project", "project_id": "project:alpha"},
            now_ms=10_000,
            stale_after_ms=5_000,
        )
        self.assertEqual(summary["progress"]["observed_at_ms"], 1_000)
        self.assertEqual(summary["freshness"]["state"], "stale")

    def test_no_valid_pulse_remains_unmeasured(self) -> None:
        node = {"id": "task-1", "project_id": "project:alpha", "role": "doer", "status": "active", "virtual": False, "is_subagent": False, "proof_snapshot": {"media": []}}
        summary = console.App._progress_for_nodes([node], {"type": "project", "project_id": "project:alpha"})
        self.assertIsNone(summary["progress"])
        self.assertEqual((summary["progress_display"], summary["freshness"]["state"]), ("Unmeasured", "unavailable"))


if __name__ == "__main__":
    unittest.main()
