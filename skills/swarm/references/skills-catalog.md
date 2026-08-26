# Skill catalog and inheritance

SWARM keeps a small preferred catalog of useful workflows without granting any
skill new authority. `find-skills` from `vercel-labs/skills` is the discovery
entry. The initial shortlist also includes systematic debugging,
test-driven-development, verification-before-completion, webapp-testing, and
frontend-design. SWARM and Product QC are bundled skills and are marked
`built_in`; they are not reinstall candidates.

The console catalog records source repository, path, ref, version, review state,
installed state, last checked time, and informational popularity/audit metadata.
Candidate or unknown skills are fail-closed. A missing skill is reported as
`available_to_install`; no console or agent silently installs it.

Inheritance is resolved in this order: canonical global defaults, global
overlay, project overlay, then observed CTRL overlay. An explicit narrower
overlay wins. Matching is an allowlisted intersection of role and task kind;
unmatched skills are not injected. Only installed and approved or built-in
skills can be inherited. Skill inheritance cannot widen tools, credentials,
provider cookies, host task authority, or user-state mutation authority.

The settings API is read-only for the catalog and exposes optimistic-revision
overlays for `global/global`, observed projects, and observed CTRL IDs. Reset
deletes the narrower overlay so the global base remains authoritative.

## Distilled nine-skill shortlist

Evaluate these as patterns before installation. Distill the useful rule into a
role baseline when that is enough; install only an exact reviewed version for a
current task-local need.

| Skill | Source | Keep | Avoid |
| --- | --- | --- | --- |
| handoff | `mattpocock/skills` | Compact continuation packet; reference existing artifacts; redact secrets | Copying full history or authority into the handoff |
| research | `mattpocock/skills` | Source-heavy work in a bounded lane; primary sources; one cited result | Unbounded browsing or source dumps |
| grill-with-docs | `mattpocock/skills` | One codebase-grounded question at a time; record only durable decisions | Ritual interrogation and unnecessary ADRs |
| improve-codebase-architecture | `mattpocock/skills` | Target proven hot spots; compare a few concrete alternatives | Broad refactors or RFC ceremony without consequence |
| prototype | `mattpocock/skills` | One disposable question; capture verdict, then delete or fold | Prototype code becoming production by inertia |
| tdd | `mattpocock/skills` | Vertical red-green-refactor against public behavior | Dogmatic test-first ceremony or private-state tests |
| frontend-design | `anthropics/skills` | Deliberate product-specific direction; complexity matched to the brief | Generic template output or decorative excess |
| copywriting | `coreyhaines31/marketingskills` | Audience, page, action, specificity, customer language, honest claims | Formula stacks and interchangeable SaaS filler |
| conducting-interviews | `refoundai/lenny-skills` | Role competencies, consistent behavioral criteria, concrete past examples, bias controls | Vibe scoring or role proliferation |

Source pages are discoverable at `skills.sh/<owner>/<repo>/<skill>`. Popularity
is discovery evidence only, never security, quality, compatibility, or install
approval.
