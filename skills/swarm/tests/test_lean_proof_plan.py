from __future__ import annotations

import unittest

from skills.swarm.runtime import (
    AcceptanceContract,
    ArtifactIdentity,
    AuthorityBoundary,
    ChangedSurface,
    ChangedSurfaceKind,
    ConsequenceTier,
    DependencyReach,
    ProofClaim,
    ProofClass,
    ProofInputs,
    ReviewScope,
    RuntimeSignal,
    Swarm,
    plan_proof,
)


class LeanProofPlanTests(unittest.TestCase):
    def artifact(self) -> ArtifactIdentity:
        return ArtifactIdentity("base", "revision", "lean proof")

    def test_docs_only_selects_atomic_fast_contract_and_is_deterministic(self) -> None:
        inputs=ProofInputs(self.artifact(),(ChangedSurface(ChangedSurfaceKind.DOCS,("README.md",)),),dependency_reach=DependencyReach(known=True))
        left=plan_proof(inputs); right=plan_proof(inputs)
        self.assertEqual(left.plan_digest,right.plan_digest)
        self.assertEqual(left.tier,ConsequenceTier.T0)
        self.assertEqual(tuple(gate.id for gate in left.gates),("contracts-fast",))
        self.assertEqual(tuple(review.scope for review in left.reviews),(ReviewScope.ACCEPTANCE,))

    def test_t0_caller_cannot_assert_away_independent_acceptance(self) -> None:
        plan=plan_proof(ProofInputs(self.artifact(),(ChangedSurface(ChangedSurfaceKind.DOCS,("README.md",)),),dependency_reach=DependencyReach(known=True),self_acceptance_risk=False))
        self.assertEqual(tuple(review.scope for review in plan.reviews),(ReviewScope.ACCEPTANCE,))

    def test_unknown_runtime_reach_broadens_to_full_contracts(self) -> None:
        plan=plan_proof(ProofInputs(self.artifact(),(ChangedSurface(ChangedSurfaceKind.RUNTIME,("skills/swarm/runtime/core.py",),public=True),)))
        self.assertEqual(plan.tier,ConsequenceTier.T1)
        self.assertIn("contracts-full",tuple(gate.id for gate in plan.gates))
        self.assertNotIn("impacted-tests",tuple(gate.id for gate in plan.gates))

    def test_visual_provider_and_release_floors_are_monotonic(self) -> None:
        visual=plan_proof(ProofInputs(self.artifact(),(ChangedSurface(ChangedSurfaceKind.VISUAL,("console/static/app.js",)),),dependency_reach=DependencyReach(known=True)))
        provider=plan_proof(ProofInputs(self.artifact(),(ChangedSurface(ChangedSurfaceKind.RUNTIME,("runtime.py",)),),authority_boundaries=(AuthorityBoundary("payments",True),),declared_claims=(ProofClaim("provider mutation",ProofClass.PROVIDER),),dependency_reach=DependencyReach(known=True)))
        release=plan_proof(ProofInputs(self.artifact(),(ChangedSurface(ChangedSurfaceKind.RELEASE,(".github/workflows/release.yml",)),),dependency_reach=DependencyReach(known=True)))
        self.assertEqual(visual.tier,ConsequenceTier.T2)
        self.assertIn("console-browser",tuple(gate.id for gate in visual.gates))
        self.assertEqual(provider.tier,ConsequenceTier.T3)
        self.assertEqual(tuple(review.scope for review in provider.reviews),(ReviewScope.PLAN,ReviewScope.ACCEPTANCE))
        self.assertEqual(release.tier,ConsequenceTier.T4)
        self.assertIn("package-integrity",tuple(gate.id for gate in release.gates))
        self.assertIn("contracts-full",tuple(gate.id for gate in release.gates))
        self.assertNotIn("impacted-tests",tuple(gate.id for gate in release.gates))
        self.assertNotIn("console-browser",tuple(gate.id for gate in release.gates))
        self.assertEqual(tuple(review.scope for review in release.reviews),(ReviewScope.COMPOSED,))

    def test_runtime_failure_signal_escalates_known_impacted_selection(self) -> None:
        plan=plan_proof(ProofInputs(self.artifact(),(ChangedSurface(ChangedSurfaceKind.RUNTIME,("runtime.py",)),),dependency_reach=DependencyReach(("focused",),known=True),runtime_signals=(RuntimeSignal("selector-disagreement","focused"),)))
        self.assertIn("contracts-full",tuple(gate.id for gate in plan.gates))
        self.assertNotIn("impacted-tests",tuple(gate.id for gate in plan.gates))

    def test_legacy_acceptance_contract_retains_every_gate_without_reuse(self) -> None:
        contract=AcceptanceContract(self.artifact(),("one","two"))
        self.assertTrue(contract.proof_plan.legacy)
        self.assertEqual(contract.required_gates,("one","two"))
        self.assertTrue(all(gate.cache_policy.value=="NEVER" for gate in contract.proof_plan.gates))

    def test_configured_swarm_applies_bounded_proof_policy(self) -> None:
        swarm=Swarm(
            proof_policy_version="lean-v1-configured",
            proof_impacted_selection=False,
            proof_receipt_reuse=False,
            proof_gate_timeout_seconds=45,
            proof_transient_retry_limit=0,
        )
        plan=swarm.plan_proof(ProofInputs(self.artifact(),(ChangedSurface(ChangedSurfaceKind.RUNTIME,("runtime.py",)),),dependency_reach=DependencyReach(("focused",),known=True)))
        self.assertIn("contracts-full",tuple(gate.id for gate in plan.gates))
        self.assertTrue(all(gate.cache_policy.value=="NEVER" for gate in plan.gates))
        self.assertTrue(all(gate.timeout_seconds==45 for gate in plan.gates))
        self.assertTrue(all(gate.flake_policy.value=="NO_RETRY" for gate in plan.gates))


if __name__ == "__main__":
    unittest.main()
