# Proven-solution-first

Use an existing, fitting solution before creating a parallel one. This is a
default for better outcomes, not an obligation to reuse something merely
because it exists.

## The lean decision

1. Put the user's requested outcome, explicit constraints, approvals, safety,
   privacy, and authority boundary first.
2. For work where the choice can materially affect quality, reliability, or
   speed, look in this order: maintained project primitives, libraries already
   present in the target repo, already-available skills/plugins, documented
   platform workflows, then stable standard APIs or dependencies already
   approved by the project. Do not add a dependency solely because it appears
   on a preferred list.
3. Reuse only a solution that is available, compatible, sufficiently
   inspectable, and likely to improve the requested outcome more than its total
   cost. For a library, check accessibility, visual consistency and branding,
   bundle/runtime cost, security/licensing, maintenance, SSR/browser
   compatibility, and fit with the project's existing framework.
4. Prefer the smallest established primitive that does the job; adapt at its
   seam rather than copying its implementation or adding a wrapper by default.
5. Low-risk, obvious fits need no research log or comparison. Record the
   evidence and trade-off only when it is consequential, uncertain, or changes
   an authority, dependency, cost, or user-facing outcome.
6. Build the narrowest native solution when no candidate fits, the adaptation
   cost exceeds the benefit, or the candidate is unavailable, opaque, insecure,
   unreliable, slower/heavier, unmaintained, or conflicts with project rules.
   A dependency-free/custom path is valid when no suitable library fits or
   adoption would create more complexity than it removes.
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

## Library discovery hints

These are compact examples for discovery, not automatic approval, installation,
or dependency authority. Reuse what is already present and compatible first;
evaluate any new adoption with the checks above.

- UI foundations: Svelte/SvelteKit, shadcn-svelte, Melt UI/Skeleton; React,
  shadcn/ui, Radix UI, Headless UI, React Aria.
- Styling: Tailwind CSS.
- Data and forms: TanStack Query/Table/Virtual, React Hook Form.
- Icons: Lucide or Phosphor icons.
- Motion: Motion/Framer Motion.
- 3D/effects, opt-in only when they add material value: Three.js, React Three
  Fiber, Drei, threeui.com, React Bits. They are not default decoration.
- Charts: Recharts, ECharts, visx, Chart.js.
- Testing, where already compatible: Testing Library, Playwright, Vitest/pytest.

User-selected branding and product requirements override library defaults.

## Compact record when it matters

`Outcome → candidate(s) checked → fit/evidence → benefit versus total cost →
choice → authority/proof limit.`

Example: `Accessible product illustration → installed image-generation skill →
fits approved visual direction; faster and more controllable than CSS collage
→ use it → rendered result still needs visual review.`
