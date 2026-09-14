# Eight Lab review

## Strategy Lab verdict

The eight Labs cover the full product loop with little overlap:

| Lab | Owns |
| --- | --- |
| Product | Product direction, roadmap, priorities, pricing, and financial viability |
| Research | Research, data, analytics, evidence, and measured insight |
| Design | UX, UI, interaction, and accessibility design |
| Build | Architecture, engineering, integrations, and automation |
| Test | QA, reliability, security, recovery tests, and acceptance |
| Content | Product narrative, documentation, and publishable media |
| Growth | Acquisition, activation, retention experiments, and adoption |
| Ops | Delivery, launch, monitoring, incidents, and operational recovery |

The catalog should stay at eight. A specialized recurring area such as a Biome
Lab remains a Custom Lab under the same manifest contract.

Use the intended output to resolve boundary questions:

- Evidence or analysis that informs a decision belongs to Research.
- A product or business decision belongs to Product.
- Shipped software belongs to Build.
- Acceptance and failure evidence belongs to Test.
- Published communication belongs to Content.
- A measured adoption experiment belongs to Growth.
- Live delivery and operation belong to Ops.

## Build Lab verdict

No new Lab runtime is needed. Each Lab remains one normal task under CTRL and
uses the existing role, block, proof, review, and milestone systems. The catalog
stores only a name, outcome, suggested roles, and three short operating steps.

Progress remains block based:

| Value | State |
| --- | --- |
| `.25` | Started |
| `.5` | Handed to review |
| `.75` | Accepted |
| `1` | Completed and committed |

CTRL owns delegation. The Lab may change roles, methods, and internal order as
evidence develops, while preserving its goal, constraints, and proof boundary.
