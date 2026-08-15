# Proven-solution-first

Use an existing, fitting solution before creating a parallel one. This is a
default for better outcomes, not an obligation to reuse something merely
because it exists.

## The lean decision

1. Put the user's requested outcome, explicit constraints, approvals, safety,
   privacy, and authority boundary first.
2. For work where the choice can materially affect quality, reliability, or
   speed, look in this order: maintained project primitives, already-available
   skills/plugins, documented platform workflows, then stable standard APIs or
   dependencies already approved by the project.
3. Reuse only a solution that is available, compatible, sufficiently
   inspectable, and likely to improve the requested outcome more than its
   integration, operational, and learning cost.
4. Prefer the smallest established primitive that does the job; adapt at its
   seam rather than copying its implementation or adding a wrapper by default.
5. Low-risk, obvious fits need no research log or comparison. Record the
   evidence and trade-off only when it is consequential, uncertain, or changes
   an authority, dependency, cost, or user-facing outcome.
6. Build the narrowest native solution when no candidate fits, the adaptation
   cost exceeds the benefit, or the candidate is unavailable, opaque, insecure,
   unreliable, slower/heavier, unmaintained, or conflicts with project rules.
7. Never install, enable, authenticate, purchase, grant permissions to, send
   data to, or contact an external service just to pursue reuse without the
   authority that action requires. An installed capability is not permission to
   use it beyond its approved boundary.
8. Do not create a fixed catalog, mandate a plugin, or add a discovery ritual.
   The available environment and the task decide; absence of a fitting solution
   is normal, not a failure.
9. Keep ownership and proof unchanged: a reused workflow cannot transfer
   acceptance, conceal a substituted boundary, or turn provider behavior into
   local proof.
10. Review the choice by its delivered result. Replace or remove a reused path
    that no longer earns its cost; do not preserve it for consistency alone.

## Compact record when it matters

`Outcome → candidate(s) checked → fit/evidence → benefit versus total cost →
choice → authority/proof limit.`

Example: `Accessible product illustration → installed image-generation skill →
fits approved visual direction; faster and more controllable than CSS collage
→ use it → rendered result still needs visual review.`
