# SWARM project brief

<!-- swarm-project-brief:schema=1 -->
```json
{
  "schema_version": 1,
  "updated_at": "2026-08-30T18:30:00Z",
  "project": {
    "id": "swarm",
    "purpose": "Turn Codex into a coordinated AI engineering team with a self-maintaining project harness for plans, ownership, artifacts, proof, and decisions."
  },
  "users_outcomes": [
    "Control an AI engineering team from one place.",
    "Let SWARM build and maintain the project-management layer around everything the team produces.",
    "Keep Codex on the roadmap from goal to accepted result with transparent artifacts, decisions, and proof."
  ],
  "objective": {
    "current": "Finish and independently accept the lean SWARM core, project-manifest doctrine, and universal Codex/ChatGPT command path, then hand accepted contracts to the separate HQ CTRL.",
    "non_goals": [
      "No second backlog, queue, state store, scheduler, or acceptance authority beside SWARM.md and the Ledger.",
      "No HQ/UI implementation, package activation, browser proof, or live deployment in the lean-refactor lane.",
      "No hidden ownership, inferred provider authority, automatic user-task mutation, or acceptance by narration."
    ]
  },
  "repo": {
    "canonical": "skills/swarm",
    "surfaces": ["runtime contracts", "doctrine", "configuration", "focused tests"],
    "architecture": "One root SWARM.md declares project intent and ordered milestones; one Ledger records material truth; one universal host-authorized connector submits work; HQ derives the control surface without owning state."
  },
  "authority": {
    "ctrl": "owns intake, topology, shared-surface coordination, and composed acceptance",
    "backlog": "SWARM.md owns ordered intent and release conditions; the Ledger owns observed state and proof; HQ is a derived projection only",
    "constraints": ["Codex host owns execution", "user state wins", "independent review stays separate", "ChatGPT routes require exact host-observed capability and authorization receipts"]
  },
  "milestones": [
    {
      "id": "ledger-p1-acceptance",
      "state": "review_required",
      "owner": "01a02240-41f5-7f30-aac9-358b4e8d2813",
      "artifact": "069de0e1e573ffbcb29706f228b0f52f16a7be89",
      "release_condition": "Independent exact-object ACCEPT confirms outer outcome-digest binding, null/omitted replay parity, no pre-failure cursor or retry mutation, canonical/plugin parity, and clean custody.",
      "note": "Implementation is frozen and ancestral to current source; producer proof was interrupted by the owner's Codex usage limit."
    },
    {
      "id": "project-manifest-doctrine",
      "state": "ready_next",
      "depends_on": ["ledger-p1-acceptance"],
      "owner": "existing Persistence/source LEAD",
      "release_condition": "One concise canonical/plugin doctrine contract defines the root brief, optional digest-bound domain manifests, stable identities, Ledger authority, HQ projection rules, compatibility, and focused contrasts without a new store or service.",
      "note": "Much of the runtime already exists; this slice consolidates and locks the governing contract."
    },
    {
      "id": "chatgpt-codex-connection",
      "state": "in_progress",
      "depends_on": ["ledger-p1-acceptance"],
      "owner": "source integration lane",
      "release_condition": "An existing local MCP bridge is selected, the thin SWARM adapter and setup path are tested, and the remaining Secure MCP Tunnel plus ordinary ChatGPT write/read-back proof is explicitly tracked as an external acceptance gate.",
      "note": "Codexify is the selected bridge; SWARM owns only read-only domain projections and bounded local telemetry."
    },
    {
      "id": "lean-core-composed-review",
      "state": "planned",
      "depends_on": ["project-manifest-doctrine", "chatgpt-codex-connection"],
      "owner": "01a0317c-1c9a-7490-805f-f50b803c7985",
      "release_condition": "Independent hostile simplicity review finds no material duplicate authority, competing state, broken role boundary, uncovered regression, or unsupported claim; focused and mirror proofs pass on one immutable source object."
    },
    {
      "id": "hq-contract-handoff",
      "state": "planned",
      "depends_on": ["lean-core-composed-review"],
      "owner": "01a046b7-a279-7b43-a871-76c0ff4d7c3b",
      "release_condition": "The separate HQ CTRL receives the accepted source SHA/tree/parent, schemas, exact paths, proof, review verdicts, and claim limits before package, activation, or browser work."
    },
    {
      "id": "hq-live-delivery",
      "state": "in_progress_separate_lane",
      "owner": "01a046b7-a279-7b43-a871-76c0ff4d7c3b",
      "release_condition": "HQ source and plugin mirrors are coherent, the accepted package is activated, and fresh loopback plus Chrome evidence proves the intended control surface.",
      "note": "Live localhost currently serves an older shell; HQ owns reconciliation and deployment."
    }
  ],
  "decisions": [
    "SWARM is distributed as a Codex plugin/workflow only.",
    "Each project has exactly one root SWARM.md brief; optional domain manifests are digest-bound references, never competing project state.",
    "SWARM.md is the canonical backlog for intent; the Ledger is canonical for observed progress and proof; HQ derives both without becoming an authority.",
    "ChatGPT is an optional direct MCP client through an existing local bridge, never a second SWARM authority or agent runtime.",
    "A design set has exactly one selected candidate; every other candidate is rejected after selection."
  ],
  "ownership": {
    "ctrl": "01a046f8-dfef-7351-a9b1-9fe41a8cd594",
    "lanes": [
      "Persistence/source: 01a02240-41f5-7f30-aac9-358b4e8d2813",
      "Architecture/review: 01a0317c-1c9a-7490-805f-f50b803c7985",
      "Security: 01a02dbf-cc38-7df0-a8f1-82a7d909b36c",
      "Separate HQ/UI CTRL: 01a046b7-a279-7b43-a871-76c0ff4d7c3b"
    ]
  },
  "proof_acceptance": {
    "basis": "typed artifact-bound proof and independent acceptance",
    "claim_limit": "Source and focused-contract evidence do not prove host, browser, deployment, or served-tier behavior."
  },
  "risks_blockers": [
    "Ledger candidate 069de0e is not independently accepted yet.",
    "The Persistence LEAD hit its Codex usage limit before returning the final immutable receipt.",
    "Codexify is not installed on the current host, so Secure MCP Tunnel setup and live ordinary-Chat write/read-back remain unverified.",
    "HQ live localhost serves an older shell and source/plugin UI mirrors are under separate reconciliation.",
    "Host transport and live execution receipts remain external gates when not observed."
  ],
  "links": [
    "skills/swarm/references/project-brief.md",
    "skills/swarm/references/execution-adapters.md",
    "skills/swarm/references/chatgpt-routing.md",
    "skills/swarm/references/chatgpt-local-mcp.md",
    "skills/swarm/references/lean-core-reset-architecture.md",
    "skills/swarm/references/decision-set.md",
    "skills/swarm/references/review-contract.md"
  ]
}
```
