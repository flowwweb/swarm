from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.progress_events import (
    MATERIAL_EVENT_FIELDS,
    TOPOLOGY_FIELDS,
    ProgressEventError,
    validate_progress_pulse,
    write_progress_pulse,
)


class ProgressEventTests(unittest.TestCase):
    @staticmethod
    def pulse(*, observed_at_ms: int = 10, completed_units: int | None = None) -> dict:
        progress = None
        if completed_units is not None:
            progress = {
                "receipt_id": f"material-{completed_units}",
                "plan_id": "plan-alpha",
                "previous_plan_id": None,
                "unit_id": "unit-build",
                "unit_kind": "milestone",
                "total_units": 4,
                "completed_units": completed_units,
                "basis": "Accepted milestones",
                "observed_at_ms": observed_at_ms,
                "source": "task_owner:local",
            }
        return {
            "schema_version": 1,
            "source": "swarm_local_progress_sidecar",
            "receipt_type": "swarm_ctrl_project_pulse",
            "task_id": "task-1",
            "project_id": "project:alpha",
            "pulse_receipt": f"pulse-{observed_at_ms}",
            "observed_at_ms": observed_at_ms,
            "state": "in_progress",
            "progress": progress,
            "eta_report": None,
        }

    def test_writer_atomically_replaces_one_bounded_latest_pulse_per_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            codex_home = Path(directory) / "codex"
            first = write_progress_pulse(codex_home, self.pulse(observed_at_ms=10))
            second = write_progress_pulse(codex_home, self.pulse(observed_at_ms=20, completed_units=1))
            files = list((codex_home / "swarm" / "progress-pulses").glob("*.json"))
            self.assertEqual((first["status"], second["status"], len(files)), ("written", "written", 1))
            stored = validate_progress_pulse(json.loads(files[0].read_text(encoding="utf-8")))
            self.assertEqual((stored.observed_at_ms, stored.progress.completed_units), (20, 1))
            unchanged = write_progress_pulse(codex_home, self.pulse(observed_at_ms=20, completed_units=1))
            self.assertEqual(unchanged["status"], "unchanged")
            heartbeat = write_progress_pulse(codex_home, self.pulse(observed_at_ms=30))
            stored = validate_progress_pulse(json.loads(files[0].read_text(encoding="utf-8")))
            self.assertEqual((heartbeat["status"], stored.observed_at_ms, stored.progress.completed_units), ("written", 30, 1))
            with self.assertRaisesRegex(ProgressEventError, "observed high-water"):
                write_progress_pulse(codex_home, self.pulse(observed_at_ms=29))

    def test_unknown_or_privacy_fields_fail_closed(self) -> None:
        for field in ("prompt", "response", "tool_calls", "credentials"):
            payload = {**self.pulse(), field: "private"}
            with self.subTest(field=field), self.assertRaisesRegex(ProgressEventError, "unsupported field"):
                validate_progress_pulse(payload)

    def test_eta_report_reuses_forecast_shape_without_embedded_progress_units(self) -> None:
        payload = self.pulse()
        payload["eta_report"] = {
            "receipt_type": "swarm_task_owner_forecast",
            "source": "task_owner:local",
            "receipt": "eta-1",
            "task_id": "task-1",
            "project_id": "project:alpha",
            "reason_code": "state_change",
            "short_reason": "Owner refreshed the current forecast.",
            "baseline": {"eta_start_ms": 20, "eta_end_ms": 40, "confidence": 70},
            "current": {"eta_start_ms": 20, "eta_end_ms": 40, "confidence": 70, "status": "in_progress", "progress_basis": {"receipts": ["eta-1"]}},
        }
        self.assertEqual(validate_progress_pulse(payload).eta_report["receipt"], "eta-1")
        payload["eta_report"]["current"]["progress_basis"]["plan_units"] = {"completed_units": 4}
        with self.assertRaisesRegex(ProgressEventError, "receipt identities only"):
            validate_progress_pulse(payload)

    def test_schema_v2_topology_fields_are_factual_and_private_content_is_absent(self) -> None:
        self.assertEqual(
            TOPOLOGY_FIELDS,
            {
                "node_kind", "input_receipt_ids", "dispatch_receipt_id",
                "completion_receipt_id", "cost_receipt_ids", "release_receipt_ids",
            },
        )
        self.assertIn("topology", MATERIAL_EVENT_FIELDS)
        self.assertTrue({"prompt", "response", "tool_calls", "credentials"}.isdisjoint(MATERIAL_EVENT_FIELDS | TOPOLOGY_FIELDS))


if __name__ == "__main__":
    unittest.main()
