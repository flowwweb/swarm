from __future__ import annotations

import unittest

from skills.swarm.runtime import StorageGuard, StorageLaneContract, StorageRecovery, StorageTarget, InvariantError


class StorageContractTests(unittest.TestCase):
    def contract(self, *, guards=None, recovery=StorageRecovery.COPY_VERIFY_REMOVE):
        root="C:\\bounded\\storage-target"
        return StorageLaneContract(
            "storage-lead",
            (StorageTarget("target-a",root),),
            (root,),
            tuple(guards or StorageGuard),
            recovery,
            "receipt:post-target",
            "receipt:post-free-space",
            "receipt:independent-review",
        )

    def test_storage_contract_is_typed_guarded_and_non_executing(self):
        contract=self.contract()
        self.assertEqual(contract.recovery,StorageRecovery.COPY_VERIFY_REMOVE)
        self.assertTrue({StorageGuard.EXACT_ROOT,StorageGuard.ACTIVE_PROCESS,StorageGuard.LIVE_LOG,StorageGuard.DATABASE,StorageGuard.DIRTY_WORK}.issubset(contract.guards))
        self.assertFalse(contract.pressure_alone_authorizes_mutation)
        self.assertFalse(hasattr(contract,"execute"))
        self.assertFalse(hasattr(contract,"move"))

    def test_storage_contract_rejects_missing_guard_or_unbound_root(self):
        with self.assertRaisesRegex(InvariantError,"requires typed exact-root"):
            self.contract(guards=(StorageGuard.EXACT_ROOT,StorageGuard.ACTIVE_PROCESS,StorageGuard.LIVE_LOG,StorageGuard.DATABASE))
        with self.assertRaisesRegex(InvariantError,"bind to an exact declared root"):
            StorageLaneContract("storage-lead",(StorageTarget("target-a","C:\\other"),),("C:\\bounded\\storage-target",),tuple(StorageGuard),StorageRecovery.RECOVERABLE_MOVE,"target","space","review")

    def test_storage_contract_rejects_wildcard_root(self):
        with self.assertRaisesRegex(InvariantError,"exact non-wildcard root"):
            StorageTarget("target-a","C:\\bounded\\*")


if __name__ == "__main__":
    unittest.main()
