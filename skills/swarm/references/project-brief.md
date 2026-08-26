# Canonical project brief

`SWARM.md` is the one living project brief at the exact project root. It is a
concise, human-readable context and provenance record, not an append-only log,
README duplicate, PRD, prompt archive, or acceptance authority. A project may
have deeper sources, but only this file is the intake brief bound to its first
topology plan.

## Required shape

The file has a `swarm-project-brief:schema=1` marker and one JSON object in a
`json` fence. The object contains these fields:

| Field | Meaning |
| --- | --- |
| `schema_version`, `updated_at` | Supported schema and UTC update time |
| `project` | Stable identity and purpose |
| `users_outcomes` | Users and intended outcomes |
| `objective` | Current objective and explicit non-goals |
| `repo` | Canonical repository, mutable surfaces, and architecture summary |
| `authority` | CTRL ownership, constraints, and user authority |
| `milestones`, `decisions` | Current state and material decisions |
| `ownership` | Active CTRL and lanes, without inventing owners |
| `proof_acceptance` | Required proof, accepting route, and claim limits |
| `risks_blockers` | Current risks and exact blockers |
| `links` | Pointers to deeper sources, never raw prompt text |

Values must be finite, JSON-serializable, and free of secrets, credentials,
raw prompts, access tokens, private keys, or unbounded logs. The brief digest is
the SHA-256 of its canonical UTF-8 JSON payload and is distinct from artifact
and acceptance digests.

## Intake and dispatch gate

Before a new SWARM project routes work, CTRL resolves exactly one root
`SWARM.md`, rejects a missing/non-regular file, validates the schema and
required fields, and binds its digest to the intake receipt and the frozen
topology plan. Until all three bindings match, dispatch is `UNREADY` and no
lane is created or reused for that project. The brief supplies context and
provenance; it cannot close proof, review, acceptance, or a user decision.

An older brief is migrated only through a deterministic schema transform with
the original content retained for review and a new digest recorded. An
unrecognized or incompatible schema fails visibly with the exact migration
boundary; it is never guessed, overwritten, or silently treated as current.
CTRL owns the file. Lanes may propose a change, but one atomic update occurs
only at intake or a meaningful material boundary, with the reason, owner,
changed fields, and new digest recorded. Routine narration, token activity,
heartbeat, and cosmetic timestamp changes do not update it.

The brief does not grant model, tool, browser, provider, destructive, host-task,
Git, release, or acceptance authority. Codex host execution remains the only
execution surface; external-provider wording in proof contracts describes real
service evidence only.
