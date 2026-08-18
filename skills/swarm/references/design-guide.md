# Compact design guide

Use this guide for design generation and review. It is a compact operational
view derived from an evidence-backed design constitution.

## Judge in this order

1. Real product truth and content
2. The user's goal, context, and primary decision
3. Hierarchy and information architecture
4. Interaction, feedback, control, and recovery
5. Loading, empty, partial, error, conflict, and completion states
6. Accessibility and alternative input
7. Responsive and platform context
8. Visual, motion, and verbal craft

## Rules

- Default new user-facing design work to built-in ImageGen mockups before
  implementation. Use ImageGen for screens, page compositions, responsive
  directions, and raster visual assets so the user can review the direction
  first.
- Do not replace that default with composites, screenshot edits, raster
  recolors, or hand-built placeholder images. Use native/vector/code-native
  work only when the artifact is inherently native (for example an icon,
  vector mark, or CSS layout) or the user explicitly approves the exception;
  keep generation, selection, implementation, and rendered acceptance as
  separate gates.
- Classify the visual artifact before reviewing it:
  - **Directional mockup**: an ImageGen or design study used to judge the user
    job, hierarchy, content, interaction idea, palette, and overall craft.
    Small generator drift in dimensions, shell geometry, wordmarks, avatars,
    or exact pixels is expected and is not a failure. Capture it as a short
    implementation handoff note.
  - **Binding visual spec**: a user-approved direction or explicitly binding
    reference that constrains the implementation. Review major composition,
    hierarchy, palette, content, and prohibited deviations; require exact
    geometry or asset fidelity only when the task says so.
  - **Implementation/runtime evidence**: a code-owned screen, compositor
    output, or browser/device capture. Here exact behavior, responsive layout,
    accessibility, and declared asset fidelity are real acceptance gates.
- Never apply implementation-grade pixel or asset gates to a directional
  mockup. Escalate only major drift that changes the requested user job,
  violates an explicit must-have, introduces unsafe or misleading content, or
  makes the direction unusable to evaluate.
- This classification is intent-driven and extensible, not tied to a project,
  route, brand, or fixed screen geometry. If intent is ambiguous, choose the
  least restrictive useful class and state the assumption. Keep dimensions,
  asset identities, and pixel thresholds in a binding artifact contract only
  when the user or project explicitly requires fidelity.
- Make the real task obvious before adding explanation or decoration.
- Give every screen one clear primary decision; progressively disclose detail.
- Show system status, accepted input, change, consequence, and next action.
- Use the user's language and name real objects; remove implementation-speak.
- Preserve work and provide cancel, undo, retry, and recovery in proportion to risk.
- Prefer recognition over recall; expose relevant state, options, and examples.
- Treat accessibility as design: contrast, non-color cues, labels, focus, order,
  keyboard/alternative input, timing, and error recovery. Make authored pointer
  targets at least 24 by 24 CSS pixels or satisfy WCAG 2.2's defined exceptions;
  a small glyph may retain a larger hit area.
- Reuse patterns for comprehension, not uniformity. Adapt to task and platform.
- Inspect the complete rendered product with real content at relevant viewports.
- Refine spacing, alignment, typography, icon weight, motion, copy, and optical
  balance when the change improves clarity, hierarchy, brand fit, or perceived
  quality. Do not spend generation or review cycles on expected ImageGen drift,
  tiny optical differences, or taste disputes that do not change the user job.
  Stop after the direction clears the user-goal and major-risk threshold; save
  finer craft polish for implementation review.
- Keep design refinement inside design surfaces; it cannot justify unrelated
  architecture, process, or scope churn.
- State whether a rule is an invariant, contextual default, or taste direction.
  Do not turn a persuasive teardown into universal law.

## Review output

For each material issue, show the artifact class, observed state, why it matters
in this context, a concrete correction, and a good/counterexample when useful.
Embed the rendered evidence. Separate standards, observed behavior, reviewer
taste, and expected generator drift. Directional mockup findings should be
reported as **KEEP**, **NOTE FOR IMPLEMENTATION**, or **REJECT DIRECTION**;
reserve rejection for a major user-job, must-have, safety, or truth failure.
