from __future__ import annotations

import unittest

from skills.swarm.runtime import DedupDecision, Swarm


class UsageSaverRuntimeTests(unittest.TestCase):
    def test_usage_saver_marks_existing_owner_reuse_and_canonical_dedup(self) -> None:
        swarm = Swarm(usage_saver=True)
        swarm.artifact_index["canonical@v1:work"] = "task-a"
        self.assertEqual(swarm.dedup("canonical@v1:work"), DedupDecision.REUSE)
        self.assertEqual(swarm.efficiency_ledger[-1]["reason"], "usage_saver:reuse_canonical")
        self.assertEqual(swarm.context_decision(affinity=1), "reuse")
        self.assertEqual(swarm.efficiency_ledger[-1]["reason"], "usage_saver:reuse_current_owner")

    def test_usage_saver_marks_noncritical_spawn_refusal(self) -> None:
        swarm = Swarm(usage_saver=True)
        self.assertFalse(swarm.should_spawn(independent=True, critical_path=False))
        self.assertEqual(swarm.efficiency_ledger[-1]["reason"], "usage_saver:refuse:noncritical")


if __name__ == "__main__":
    unittest.main()
