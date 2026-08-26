# SWARM project brief

<!-- swarm-project-brief:schema=1 -->
```json
{
  "schema_version": 1,
  "updated_at": "2026-08-26T00:00:00Z",
  "project": {
    "id": "swarm",
    "purpose": "Codex-native multi-agent workflow and runtime contracts for durable, reviewable work."
  },
  "users_outcomes": [
    "Give people visible ownership, durable progress, and truthful proof.",
    "Keep routing shallow, bounded, and under direct user control."
  ],
  "objective": {
    "current": "Maintain the smallest safe topology, evidence, and acceptance path for SWARM.",
    "non_goals": [
      "No alternate agent host or provider execution support.",
      "No hidden ownership, automatic user-task mutation, or acceptance by narration."
    ]
  },
  "repo": {
    "canonical": "skills/swarm",
    "surfaces": ["runtime contracts", "doctrine", "configuration", "focused tests"],
    "architecture": "A Codex plugin routes visible CTRL, LEAD, and DOER work through typed state, evidence, and independent review."
  },
  "authority": {
    "ctrl": "owns intake, topology, shared-surface coordination, and composed acceptance",
    "constraints": ["Codex host owns execution", "user state wins", "independent review stays separate"]
  },
  "milestones": [
    {"id": "brief-contract", "state": "active", "note": "Root brief and boundary contracts are canonical."}
  ],
  "decisions": [
    "SWARM is distributed as a Codex plugin/workflow only.",
    "A design set has exactly one selected candidate; every other candidate is rejected after selection."
  ],
  "ownership": {
    "ctrl": "current user-authorized CTRL",
    "lanes": ["existing policy/topology owner", "separate Persistence owner", "separate UI owner"]
  },
  "proof_acceptance": {
    "basis": "typed artifact-bound proof and independent acceptance",
    "claim_limit": "Source and focused-contract evidence do not prove host, browser, deployment, or served-tier behavior."
  },
  "risks_blockers": [
    "Host transport and live execution receipts remain external gates when not observed."
  ],
  "links": [
    "skills/swarm/references/project-brief.md",
    "skills/swarm/references/decision-set.md",
    "skills/swarm/references/review-contract.md"
  ]
}
```
