# Compact review contract

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
5. **Product quality**: behavior and copy help the user act; affected visual,
   interaction, accessibility, responsive, and performance surfaces are
   inspected rather than inferred. Visual, design, and image-generation work is
   distinctive and context-specific by default; generic, boring, or template
   output is a finding unless the user requested it. Do not reward novelty,
   decoration, maximalism, or visual noise: intentional project fit is the bar.
6. **Evidence**: tests observe behavior; failures and timeouts stay failures;
   static, local, browser, authenticated, provider, deployed, device, and human
   proof are not conflated.

## Make evidence reviewable at a glance

Treat the reviewer response itself as the primary review surface. Embed the
highest-signal evidence instead of returning only paths or folders:

- for visual or interaction work, include representative reference/candidate
  or before/after screenshots at the relevant viewport or state;
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

Rank findings `P0` destructive/security/data loss, `P1` blocked core outcome,
`P2` confusing or fragile behavior/maintainability, and `P3` bounded polish.
P0-P2 block approval. A correction must use the narrowest established primitive
and add user-observable regression evidence. REVIEW is read-only by default. If
MOTHER transfers one narrow correction after the prior owner releases it,
REVIEW returns CORRECT and a different independent reviewer or context validates
the edit. REVIEW APPROVE is evidence for acceptance, not portfolio acceptance:
LEAD may accept a child handoff into its domain, while MOTHER alone accepts the
integrated outcome.

`APPROVE` requires all must-haves, no unresolved P0-P2, proportionate proof, and
honest claim limits. `CORRECT` names the selected repair and proof, or presents
options for the acceptance owner when the governing rule is the disputed part.
`BLOCKED` names the exact missing authority, environment, credential, product
decision, or external state. Do not produce a narrative verdict without
inspecting the artifact.
