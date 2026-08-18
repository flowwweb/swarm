# Compact review contract

Before completion, release, or archive, audit the explicitly enabled and attached request ledger. Disabled or enabled-but-unattached continuity is `UNVERIFIED`, never evidence of enforcement. Every accepted request must be terminal through current evidence-backed acceptance or explicit user cancellation/supersession. Unresolved, provisional, corrupt, orphaned, or stale-ledger state is `UNVERIFIED`; stored terminal history or event cursors cannot replace the current task, artifact, gate, independent review, published proof, or accepting route.

## Minimum independent review

Do not repeat the same review under different names. The ProofPlan chooses the
minimum independent review that matches consequence and evidence:

| Tier | Required proof and review |
| --- | --- |
| T0 atomic/docs | Focused deterministic contract plus light independent acceptance; callers cannot assert it away |
| T1 ordinary code | Fast contracts plus impacted proof; one combined source-and-acceptance review |
| T2 visual/browser | T1 plus exact final browser/visual evidence; one combined browser/source/acceptance review |
| T3 provider/security/data | Plan review before mutation, authority/failure proof, then final acceptance |
| T4 release | Reuse unchanged accepted lanes, verify one immutable package across environments, then one composed release review |

Unknown dependency reach or missing impact evidence broadens the plan. After a
correction, rerun the failed proof and every dependent gate, not unrelated
accepted work. A failed or timed-out prerequisite stops its dependent gates
until the prerequisite passes or the plan is revised.

Browser proof is selected only for affected or claimed browser/visual surfaces.
Release escalation replaces impacted proof with broad proof; it does not run
both. T0 independent acceptance cannot be omitted by a caller asserting that
self-acceptance risk is absent.

For consequential implementation, REVIEW first judges an immutable plan artifact.
`PLAN PASS` authorizes implementation only; it cannot accept code, behavior,
deployment, or the portfolio. Corrections create a new plan revision and return
to plan review. After implementation and exact named proof are frozen, an
independent `ACCEPTANCE` review judges that completed artifact. Any correction
creates a new artifact identity, reopens its gates, and requires a fresh final
review. CTRL composes only independently accepted lane artifacts.

A current stable gate receipt may be reused only when its plan, exact command
and gate spec, artifact, input closure, environment, authority context, proof
class, declared-claim coverage, and freshness rules
still match after runtime re-observation. Cache is disposable continuity, not
acceptance. External proof has bounded freshness. `TIMEOUT` never passes; one
typed transient retry is the maximum before broadening or blocking.

Provider, deployed, device, and human gates are never satisfied by a shell
command, in-process signer, or caller-authored receipt. They remain `UNVERIFIED`
until an isolated host verifier records a typed observation bound to its
evidence digest, observation time, proof class, plan, gate spec, artifact,
environment, and authority context. Missing, forged, mismatched, replayed,
expired, or plugin-runtime-only observations remain open.

## Classify proof and final visual artifacts honestly

Classify runtime proof by the authority and transport actually exercised, not
the number of clients or tabs. Mocks, request interception, fixtures, and
in-memory substitutes prove only that substituted boundary; name it in the
receipt and leave local-session, emulator, provider, network, deployed, or
device boundaries that were not exercised `UNVERIFIED`.

Before accepting a visual claim, inspect the exact final rendered frame before
trusting DOM geometry or receipts. The claimed primary substrate and relevant
user context must be visibly real; a correct overlay cannot upgrade a blank,
fallback, mocked, placeholder, or failed substrate. Relevant console warnings,
page errors, and failed requests block a clean claim until explained by a
narrower claim.

For taste-led generation, a clear user direction permits generation while a
reserved choice requires candidates and a wait. Classify each supplied reference
as loose inspiration or binding. For a binding reference, make a fidelity
checklist for geometry/composition, typography/letterforms, palette, hierarchy,
and prohibited deviations, then inspect the exact delivered artifact beside the
reference in delivered context after every transformation. An intermediate
preview, source, filename, manifest, or conversion receipt cannot prove final
fidelity. Loose inspiration carries only the direction the user assigned, never
a counterfeit likeness claim.

### Directional mockups are not pixel-perfect implementation plates

Before assigning a visual finding, declare the artifact class:

- **DIRECTIONAL_MOCKUP** — an ImageGen or design study intended to help the user
  choose a direction. Judge the user job, hierarchy, content, interaction idea,
  palette, brand feel, and overall quality. Small expected generator drift in
  canvas dimensions, shell geometry, wordmarks, avatars, or exact pixels is a
  `NOTE_FOR_IMPLEMENTATION`, never a rejection by itself.
- **BINDING_VISUAL_SPEC** — a selected direction or explicitly binding reference
  that constrains implementation. Gate major composition, hierarchy, palette,
  content, and prohibited deviations; require exact geometry or asset fidelity
  only when the task declares that requirement.
- **IMPLEMENTATION_EVIDENCE** — code-owned output, compositor plate, browser
  capture, device capture, or release artifact. Gate exact behavior,
  responsive layout, accessibility, declared assets, and any explicit visual
  fidelity contract.

For `DIRECTIONAL_MOCKUP`, do not issue P1/P2 or `REJECT` for ordinary generator
variation in canvas, shell geometry, identity rendering, or exact pixels. Those
are implementation handoff notes unless the user or project contract made a
specific fidelity requirement binding. Escalate only when the drift changes the
requested user job, contradicts an explicit must-have or prohibited element,
introduces unsafe or misleading content, or makes the direction impossible to
evaluate. The correct result is usually `KEEP` plus a short implementation
handoff. Do not spend another generation/review cycle eliminating expected
variation before the user chooses the direction.

The artifact classes are generalized policy, not a project template. Infer the
least restrictive class that still answers the user's question, state that
assumption, and let explicit user or project authority override it. Never add
screen-specific dimensions, asset names, identity names, pixel thresholds, or
route-specific gates to global doctrine; put those in the artifact's own
contract only when fidelity is explicitly required.

`SOURCE_SEMANTICS` checks the implementation and may return useful findings, but
it cannot set final `review_passed`. `ACCEPTANCE` checks the declared immutable
`ArtifactIdentity` against its `AcceptanceContract`. It passes only when every
named gate has an exact-artifact `PASS` receipt. Missing, `FAIL`, `TIMEOUT`, and
stale-artifact receipts remain open. A legacy `passed=True` boolean is rejected.

Each task declares `CODE`, `NON_CODE`, or `OTHER` and a stable owning LEAD
identity when delegated. Assignment and warm reuse bind the task to the
selected worker's actual LEAD. `CODE` requires at least one named gate. Only
non-artifact `NON_CODE` work permits an empty contract; `OTHER`, `CODE`, and
artifact-producing lanes reject it, including a later switch after registration. The
bound LEAD owns lane integration, incident consultation, gate execution/recording,
and lane completion. CTRL may complete only direct accepted work and cannot
close a LEAD-owned lane. REVIEW independently verifies the exact artifact and receipts;
it never converts source-only approval into acceptance. CTRL surfaces the verdict
and refuses portfolio acceptance when the acceptance receipt is absent; it does
not rerun or impersonate the lane owner. CTRL alone composes accepted lanes into
final portfolio acceptance.

An independent reviewer judges an inspectable artifact. Use a user-visible
REVIEW task for multi-lane, cross-owner, or consequential work; use a bounded
internal reviewer for one cohesive low-risk change. Read repository and product
authority, the outcome contract, actual changed surfaces, and available runtime
evidence. Do not inherit the builder's rationale as truth.

```text
REVIEW - artifact

Artifact/revision: exact immutable review boundary.
Outcome: user result and non-negotiables it must preserve.
Risk/claims: consequence tier and proof classes claimed.
Inspect: changed surfaces plus relevant integrated behavior.
Exercise: happy path and credible failure/recovery states.
Subtract: duplicate authority, speculative layers, unnecessary copy/config/tasks.
Proof: exact checks, rendered/provider/live evidence, and claim limits.
Evidence surface: embedded screenshots, comparisons, tables, or excerpts that
make the verdict reviewable at a glance; links are supplemental.
Composed acceptance: inspect the integrated whole, requirement ledger, and
every required proof state; lane-local approval cannot substitute.
Visual direction: context-specific intent, generic/template risks, and any
explicit request for conventional or restrained treatment.
Verdict: APPROVE, CORRECT, or BLOCKED with P0-P3 findings.
Options: viable artifact, rule, or product-decision responses and tradeoffs.
Return: accepting owner and smallest next action.
```

Review in this order:

1. **Outcome**: requested capability is present; no must-have was silently
   narrowed, disabled, mocked, deferred, or relabeled successful.
2. **Trust**: domain rules, permissions, data, security, consequential writes,
   and authority live at the correct boundary.
3. **Continuity**: meaningful validation, loading, empty, error, retry,
   reconnect, conflict, and recovery behavior preserves user work and truth.
4. **Subtraction**: existing primitives are reused; no speculative abstraction,
   duplicate state/authority, unjustified dependency, flag, UI, or task layer.
5. **Product quality**: every visible UI element helps the user act or understand
   the current state; affected visual, interaction, accessibility, responsive,
   and performance surfaces are inspected rather than inferred. Keep conditional
   recovery controls hidden until their recovery state applies, and remove
   self-evident identity or duplicate cues. Prefer conventional icon-only actions
   when their meaning is obvious, but require an accessible name and adequate
   target; ambiguous or consequential actions retain visible text. Minimalism
   cannot justify mystery icons, inaccessible targets, or removal of necessary
   state. Visual, design, and image-generation work is distinctive and
   context-specific by default; generic, boring, or template output is a finding
   unless the user requested it. Do not reward novelty, decoration, maximalism,
   or visual noise: intentional project fit is the bar.
6. **Evidence**: tests observe behavior; failures and timeouts stay failures;
   static, local, browser, authenticated, provider, deployed, device, and human
   proof are not conflated.

Before reading detailed receipts for a visual claim, perform a first-glance user
reality check on the exact final frame. Name the primary surface the user needs
to see and verify that its real content and context are visibly present. A map
without geography, a chart without data, media without the requested subject,
or a page showing only a correct overlay on a blank, mocked, placeholder, failed,
or fallback substrate is a failed visual result. A test label, DOM bounds,
screenshot file, selector pass, or internally correct overlay cannot upgrade the
missing substrate. Inspect relevant console errors, warnings, page errors,
network failures, and fallback telemetry before accepting a clean rendered
claim. Also review the ordinary task at a glance: duplicate actions, controls
that compete for the same job, and always-visible detail that obscures the
primary decision are product findings even when every control functions.

## Make evidence reviewable at a glance

Treat the reviewer response itself as the primary review surface. Embed the
highest-signal evidence instead of returning only paths or folders:

- for visual or interaction work, include representative reference/candidate
  or before/after screenshots at the relevant viewport or state;
- when images are part of the user-facing result, render representative,
  high-signal images inline with absolute Markdown image syntax such as
  `![caption](/absolute/path/to/image.png)` (or an equivalent native image
  block); links may supplement the embed for provenance or the complete
  inventory, but never replace it;
- for repeated checks, mappings, or matrices, include a compact table;
- for source, contract, log, network, or provider findings, include the shortest
  useful excerpt or receipt with sensitive data removed;
- caption every item with what was observed and whether it is static, local,
  browser, authenticated, provider, deployed, device, or human evidence.

Links and complete evidence inventories are supplemental. If capture is
blocked, name the exact blocker and embed the best available lower-class proof;
never substitute an evidence locator, stale screenshot, or static excerpt for
the missing runtime class. When the packet is too large, show representative
coverage and state exactly what was omitted.

For visual or interaction work, inspect the composed rendered product at every
requested responsive viewport and state before `APPROVE`, acceptance, or
deployment. Treat a loose-inspiration reference only as the direction the user
assigned to it; it is not a likeness gate. For an explicitly binding reference,
compare the exact final artifact side by side in delivered context against its
geometry/composition, typography/letterforms, palette, hierarchy, and prohibited
deviations. Generic thematic similarity cannot pass that fidelity gate. A
component crop, isolated route, or lane-local screenshot is weaker evidence and
cannot close the composed surface. If a binding reference or required capture
is unavailable, say so, retain `UNVERIFIED`, and return `BLOCKED` or `CORRECT`
rather than silently lowering the visual bar.

## Review the rule as well as the artifact

Do not turn every guideline mismatch into an opinionated implementation order.
First classify the governing standard:

- **Invariant**: safety, authority, legal, destructive-action, explicit product
  contract, or another requirement that cannot be traded away by preference.
- **Contextual default**: a good-faith accessibility, visual, architecture, or
  workflow baseline whose benefit and cost vary with the actual users and task.
- **Preference**: a reasonable direction without enough authority or evidence
  to act as a gate by itself.

For a contextual default, report the observed mismatch and offer the smallest
credible options. Include keeping the rule and changing the artifact, narrowing
the rule for the proven context, or gathering evidence when either choice could
be right. Weigh user comfort, error consequence, frequency, input method,
discoverability, consistency, accessibility, maintenance cost, and available
runtime or user evidence. State which option is recommended and why, while
separating observed fact, governing authority, and reviewer judgment.

For example, a 44px target can be a useful touch-first default without being a
universal invariant for every compact game control. A reviewer may still block
acceptance when the choice is material, but must consider whether a smaller,
well-spaced, keyboard-accessible control better fits experienced players and
the interaction density. Do not silently weaken an actual minimum requirement;
identify the authority and ask the acceptance owner to choose when it conflicts
with the product context.

## Apply a significance gate outside design

For every non-design finding, state the concrete consequence of leaving it and
the observable improvement expected from changing it. Prefer a metric; when a
direct metric is impractical, name specific evidence and a falsifiable outcome.
The expected benefit must justify the combined investigation, implementation,
review, regression, and coordination cost. Reject as nitpicks stylistic
preference, theoretical purity, speculative future-proofing, cosmetic
consistency outside design, marginal refactoring, and technically true defects
with no credible consequence. Do not record them as P3, backlog, optional
follow-up, or “while here” work. The act of reviewing is not evidence that a
change is valuable.

When the agreed outcome and proof pass with no material unresolved finding,
return `APPROVE` and stop. Do not order another pass merely because deeper
inspection could find more minor issues. Reopen review only for new evidence,
changed scope, a failed gate, or a named material risk.

For a directional mockup, one independent review pass is the default. Once the
direction is usable, truthful, and clearly helps the user choose, return
`KEEP` or `APPROVE_DIRECTION` and stop. Do not convert implementation notes into
new ImageGen attempts before the user selects a direction. A second pass needs
new evidence or a named material risk, not a desire for a cleaner pixel match.

Design review is the explicit exception, but it is still calibrated. For a
`DIRECTIONAL_MOCKUP`, critique visual, interaction, motion, copy, and craft
details only when they materially improve clarity, coherence, product fit, or
the user's decision. Treat small expected ImageGen variation and taste
differences as notes, not blockers; do not launch another generation solely to
chase pixel parity. Judge details against the requested direction and the
composed product, and keep the exception inside design surfaces. A design nit
cannot justify unrelated code, architecture, process, or scope churn. For a
`BINDING_VISUAL_SPEC` or `IMPLEMENTATION_EVIDENCE`, apply the declared fidelity
and runtime gates. In mixed reviews, classify the artifact and each finding
before applying the exception.

Rank findings `P0` destructive/security/data loss, `P1` blocked core outcome,
`P2` confusing or fragile behavior/maintainability, and `P3` bounded polish.
P0-P2 block approval. A correction must use the narrowest established primitive
and add user-observable regression evidence. REVIEW is read-only by default. If
CTRL or the owning LEAD transfers one narrow correction after the prior owner releases it,
REVIEW returns CORRECT and a different independent reviewer or context validates
the edit. REVIEW APPROVE is evidence for acceptance, not portfolio acceptance:
LEAD may accept a child handoff into its domain, while CTRL alone accepts the
integrated outcome.

REVIEW is independent of the LEAD and DOERs it inspects, and independently gates
the exact immutable integration SHA; it does not deploy, self-accept, or correct
its own reviewed work. The LEAD integrates DOER handoffs, submits the SHA, routes
and resolves REVIEW corrections, then accepts and deploys only the independently
approved SHA with rollback receipt and production proof. CTRL accepts only the
composed portfolio. A shared provider/project/channel target must show the
CTRL-managed ownership or lease receipt before the LEAD's mutation is reviewable
as safe.

`APPROVE_DIRECTION` means a directional mockup is usable for the user's
decision and has no material user-job, must-have, safety, or truth failure; it
does not authorize implementation or claim pixel/runtime parity. `APPROVE`
requires all must-haves, every required ledger proof `VERIFIED`, no
unresolved P0-P2, proportionate proof, and honest claim limits. `UNVERIFIED`
required proof blocks approval and portfolio acceptance. `CORRECT` names the selected repair and proof, or presents
options for the acceptance owner when the governing rule is the disputed part.
`BLOCKED` names the exact missing authority, environment, credential, product
decision, or external state. Do not produce a narrative verdict without
inspecting the artifact.

## Escaped-defect propagation

For a material defect found after handoff or review, the owning LEAD records one
private Git-ignored local causal trace in `.codex/swarm/incidents.jsonl`: introduction point and
owner surface, detector and earliest cheap detector, missed-gate reason,
propagation path, known cost/time lost, correction, generalization candidate,
disposition, and structured evidence references. Cross-process writes and folds
serialize without lost updates. The next matching execution brief consults
unresolved records before gate work. Daily fold promotes only distinct repeated
failure classes or demonstrably generalizable controls with contrasting regression
proof. Ineligible candidates remain pending; only an explicit reasoned API rejects. Keep
repo-specific commands, person blame, local policy, secrets, and one-off incident
wording out of global SWARM doctrine.
