# SWARM HQ Labs page

## Product decision

Labs become the preferred way to start repeatable, multi-discipline work. A Lab
is a preconfigured task template that assembles existing roles around one
question. Roles remain reusable capabilities inside the Lab. Starting a Lab
creates normal SWARM milestone, task, block, artifact, proof, and review records;
the library does not introduce another runtime or source of truth.

## Page contract

- Show four V1 templates: Strategy Lab, Build Lab, Growth Lab, and Design Lab.
- Each card carries one outcome line, a quiet `Ready` state, a role-avatar stack,
  and a chevron. The role stack explains composition without exposing role copy.
- Selecting a card reveals one field: `What should this lab answer?` and one
  action: `Start`. Only one card is expanded at a time.
- `Start a lab` focuses the first template and its question field. It does not
  open a second catalog or require a setup wizard.
- Starting creates the smallest viable Lab plan from the chosen template and
  current project context, then routes the user to the new Lab task.

## Template composition

| Lab | Outcome | Default roles |
| --- | --- | --- |
| Strategy Lab | Find the clearest path. | Strategist, Researcher, Analyst, Reviewer |
| Build Lab | Ship a working slice. | Developer, Architect, Tester, Reviewer |
| Growth Lab | Test what earns traction. | Marketer, Researcher, Analyst, Designer |
| Design Lab | Compare the strongest experience. | Designer, Researcher, Developer, Reviewer |

Role composition is a default. SWARM may substitute an equivalent available
role while preserving the Lab question, proof plan, and review boundary.

## Interaction details

- Whole-card click or chevron selects and expands a template.
- Enter submits when the question field is focused; Escape collapses it.
- Opening and closing uses a 160-200 ms height and opacity transition. Respect
  reduced motion.
- `Ready` uses a dot and text so state does not rely on color alone.
- Minimum touch target is 44 px on mobile. Focus rings use the existing orange
  accent.
- Mobile keeps the canonical compact header and a single card column. The
  selected setup stays inline; no side panel is required.

## Deliberate omissions

No Lab metrics, progress bars, tabs, long descriptions, duplicate project
selector, or task preview appears in the template library. Progress belongs on
the resulting task and hierarchy surfaces after the Lab starts.

## Visual references

- `labs-desktop.png`: desktop library and inline launch state.
- `labs-mobile.png`: responsive single-column library.
