# Design decision-set lifecycle

A design decision set is one bounded set of user-judgeable candidates owned by
one CTRL. Candidate paths and worker finals are provenance; they are not a
selection, delivery, or acceptance receipt.

At the user's selection boundary, CTRL records one atomic metadata event:

1. exactly one candidate is `SELECTED`;
2. every other candidate in the complete inventory is `REJECTED`;
3. each state is bound to the candidate's immutable artifact identity and
   content digest; and
4. the selected artifact is durably preserved with an exact hash-bound receipt
   before any rejected asset becomes cleanup-eligible.

The decision set remains open when the user has not selected, when the complete
inventory is missing, or when preservation/hash binding is absent. A duplicate,
empty, stale, or conflicting selection fails closed. A later selection cannot
silently replace the first durable `SELECTED` state; it requires a new explicit
decision set or an explicit user correction.

After preservation, rejected local binaries become first-class candidates for a
separate Storage cleanup decision, especially under disk pressure. The cleanup
receipt names each exact path, expected digest, decision-set identity, and
preservation receipt. It never accepts a glob, directory-wide sweep, guessed
path, current or undecided artifact, or the selected artifact as a target.
Storage performs cleanup only after its own exact-root, process/handle, custody,
and copy-verify-remove gates; SWARM does not delete assets and does not start a
worker, process, or service for this lifecycle. There is no glob, directory-wide
sweep, guessed path, current or undecided asset, or selected-artifact target.

The selection metadata is folded into the normal handoff/evidence event. It
does not create a new lane, bypass independent review, or turn a selected
candidate into an accepted product without the declared proof and acceptance
route. Unsupported rendering, unreadable transport, and missing receipts stay
pending rather than being inferred from silence or completion.
