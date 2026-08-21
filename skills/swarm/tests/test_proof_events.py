from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.proof_events import ProofEventError, register_proof_event


PNG = b"\x89PNG\r\n\x1a\n" + b"proof"


class ProofEventTests(unittest.TestCase):
    def test_registration_is_content_addressed_immutable_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "capture.png"
            source.write_bytes(PNG)
            event = register_proof_event(
                root / "codex",
                source,
                evidence_id="proof:one",
                task_id="task-1",
                kind="screenshot",
                caption="Settings at desktop width",
                created_at_ms=7,
            )
            self.assertEqual(event["disposition"], "PENDING")
            self.assertEqual(event["size_bytes"], len(PNG))
            media = root / "codex" / "swarm" / event["locator"]
            self.assertEqual(media.read_bytes(), PNG)
            again = register_proof_event(
                root / "codex",
                source,
                evidence_id="proof:one",
                task_id="task-1",
                kind="screenshot",
                caption="Settings at desktop width",
                created_at_ms=8,
            )
            self.assertEqual(again, event)
            with self.assertRaisesRegex(ProofEventError, "different proof event"):
                register_proof_event(
                    root / "codex",
                    source,
                    evidence_id="proof:one",
                    task_id="task-1",
                    kind="screenshot",
                    caption="Changed caption",
                    created_at_ms=7,
                )

    def test_registration_rejects_extension_only_media(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "fake.png"
            source.write_bytes(b"not an image")
            with self.assertRaisesRegex(ProofEventError, "signature"):
                register_proof_event(
                    root / "codex",
                    source,
                    evidence_id="proof:bad",
                    task_id="task-1",
                    kind="screenshot",
                    caption="Fake image",
                )

    def test_concurrent_different_events_cannot_overwrite_the_winner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "capture.png"
            source.write_bytes(PNG)

            def attempt(caption: str) -> str:
                try:
                    register_proof_event(
                        root / "codex",
                        source,
                        evidence_id="proof:race",
                        task_id="task-1",
                        kind="screenshot",
                        caption=caption,
                        created_at_ms=7,
                    )
                    return "ok"
                except ProofEventError:
                    return "rejected"

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(attempt, ("First caption", "Second caption")))
            self.assertEqual(sorted(outcomes), ["ok", "rejected"])
            events = list((root / "codex" / "swarm" / "proof-events").glob("*.json"))
            self.assertEqual(len(events), 1)


if __name__ == "__main__":
    unittest.main()
