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
