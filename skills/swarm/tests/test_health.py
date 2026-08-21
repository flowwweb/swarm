from __future__ import annotations

import hashlib
import unittest

from skills.swarm.runtime.health import HealthRecoveryRequest, RecoveryRequestType


class HealthRequestTests(unittest.TestCase):
    def test_request_is_typed_and_canonical(self) -> None:
        digest = hashlib.sha256(b"sample").hexdigest()
        request = HealthRecoveryRequest(
            request_id="health:disk:host:1",
            incident_key="disk:host:disk_degraded",
            request_type=RecoveryRequestType.CLEANUP_REVIEW,
            severity="PRESSURED",
            scope="C:\\",
            evidence_digest=digest,
            recommended_action="Review exact stale targets.",
            constraints=("No broad Docker prune.",),
            created_at_ms=1,
            expires_at_ms=2,
        )
        self.assertEqual(request.to_payload()["request_type"], "cleanup_review")
        self.assertEqual(HealthRecoveryRequest.from_payload(request.to_payload()), request)
        self.assertEqual(len(request.digest()), 64)

    def test_request_rejects_unsafe_or_malformed_data(self) -> None:
        digest = hashlib.sha256(b"sample").hexdigest()
        kwargs = {
            "request_id": "request",
            "incident_key": "incident",
            "request_type": "capacity_review",
            "severity": "DEGRADED",
            "scope": "host",
            "evidence_digest": digest,
            "recommended_action": "Review capacity.",
            "constraints": (),
            "created_at_ms": 1,
            "expires_at_ms": 2,
        }
        with self.assertRaises(ValueError):
            HealthRecoveryRequest(**{**kwargs, "recommended_action": "delete files\nnow"})
        with self.assertRaises(ValueError):
            HealthRecoveryRequest(**{**kwargs, "evidence_digest": "0" * 63})
        with self.assertRaises(ValueError):
            HealthRecoveryRequest(**{**kwargs, "request_type": "delete_processes"})


if __name__ == "__main__":
    unittest.main()
