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
  balance. Small design details compound and design nitpicking is encouraged.
- Keep design refinement inside design surfaces; it cannot justify unrelated
  architecture, process, or scope churn.
- State whether a rule is an invariant, contextual default, or taste direction.
  Do not turn a persuasive teardown into universal law.

## Review output

For each material issue, show the observed state, why it matters in this
context, a concrete correction, and a good/counterexample when useful. Embed the
rendered evidence. Separate standards, observed behavior, and reviewer taste.
