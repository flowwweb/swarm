# SWARM HQ screen comparison — 2026-09-13

This historical report retains visual references and implementation notes. Runtime captures containing private project data are excluded from the public source. Remaining historical images have not completed privacy review and do not establish current runtime, telemetry or provider acceptance.

## Coverage at a glance

| Surface | Desktop reference | Desktop live capture | Mobile reference | Mobile live capture | Evidence status |
| --- | --- | --- | --- | --- | --- |
| Overview | Console overview reference | Not retained publicly | None checked in | Not retained publicly | Reference only; no public runtime capture |
| Swarm hierarchy | Hierarchy reference | Not retained publicly | None checked in | Not retained publicly | No current runtime evidence |
| Agents | Agents reference | Not retained publicly | None checked in | None checked in | Reference only |
| Roles | Roles reference | 2026-09-12 live roles view | Roles mobile reference | 2026-09-12 live roles view | Desktop and mobile pair |
| Review | Review reference | Not retained publicly | None checked in | None checked in | Reference only |
| Assets | Approved assets reference | 2026-09-12 live assets view | None checked in | None checked in | Reference plus live render |
| Diagnostics | Approved diagnostics reference | 2026-09-12 live diagnostics view | None checked in | None checked in | Reference plus live render |
| Settings | Approved settings reference | Not retained publicly | None checked in | None checked in | Reference only |
| Project detail | Kanban/project reference | 2026-09-12 live project detail | None checked in | None checked in | Closest reference plus live render |
| Chat panel | No separate approved mockup artifact | 2026-09-12 live chat panel | None checked in | None checked in | Live evidence only |
| Usage detail | No separate approved modal mockup artifact | 2026-09-12 live usage modal | None checked in | None checked in | Live/reference capture only |
| Onboarding | Canonical slide artwork | Five fresh local captures | None checked in | None checked in | Canonical assets plus current live slides |

The 2026-09-12 images are historical live captures. The 2026-09-13 images are the newer approved-reference/current-capture set. A missing reference is called out rather than inferred from a neighboring screen.

## Desktop comparisons, stacked

### Overview

**Mockup / reference**

![SWARM console overview reference](../../artifacts/console-mockups-v2/swarm-console-overview.png)

**Live implementation capture**

No public runtime capture is retained for this desktop surface.

The reference establishes the four-stat header, project table, token burn-rate treatment, and hierarchy area. Current data binding requires separate accepted runtime evidence.

### Swarm hierarchy

**Mockup / reference**

![Swarm hierarchy reference](../../artifacts/console-mockups-v2/swarm-console-hierarchy.png)

**Live implementation capture**

No public runtime capture is retained for this section.

The reference defines the intended tree. An observed hierarchy, progress or ETA requires accepted project records; this reference is not runtime proof.

### Agents

**Mockup / reference**

![Agents reference](../../artifacts/hq-mockups-2026-09-13/agents-desktop.png)

**Live implementation capture**

No public runtime capture is retained for this surface.

The implementation must distinguish observed host tasks from accepted CTRL, LEAD, and DOER records. It must not invent an accepted hierarchy when the project feed has not supplied one.

### Roles

**Mockup / reference**

![Roles desktop reference](../../artifacts/hq-mockups-2026-09-13/roles-desktop-reference.png)

**Live implementation capture**

![Roles desktop live capture](../../docs/ui-review/screenshots/2026-09-12/screen-roles.png)

Roles are the premade role library. They do not own task progress. Detail text stays behind accordions to keep the desktop grid scannable.

### Review

**Mockup / reference**

![Review reference](../../artifacts/hq-mockups-2026-09-13/review-desktop.png)

**Live implementation capture**

The historical Review capture contains private workflow data and is not retained in the public source.

The reference keeps proof, status, and quick actions together. A current runtime comparison requires separate, privacy-reviewed evidence.

### Assets

**Mockup / reference**

![Assets approved reference](../../artifacts/hq-mockups-2026-09-13/assets-approved.png)

**Live implementation capture**

![Assets live capture](../../docs/ui-review/screenshots/2026-09-12/screen-assets.png)

The empty state is explicit. Placeholder assets are not presented as real project data.

### Diagnostics

**Mockup / reference**

![Diagnostics approved reference](../../artifacts/hq-mockups-2026-09-13/diagnostics-approved.png)

**Live implementation capture**

![Diagnostics live capture](../../docs/ui-review/screenshots/2026-09-12/screen-diagnostics.png)

The compact health summary, three checks, recent signals, and Run checks action are the intended diagnostic hierarchy.

### Settings

**Mockup / reference**

![Settings approved reference](../../artifacts/hq-mockups-2026-09-13/settings-approved.png)

**Live implementation capture**

No public runtime capture is retained for this surface.

The implementation keeps Workflow, Usage saver, and Appearance visible first. Scope and advanced controls stay behind the compact settings path.

### Project detail and task view

**Mockup / reference**

![Project task view reference](../../artifacts/console-mockups-v2/swarm-console-kanban.png)

**Live implementation capture**

![Project detail live capture](../../docs/ui-review/screenshots/2026-09-12/screen-project-detail.png)

The live project view renders observed host work and keeps unsupported ledger values unavailable instead of guessing progress, ETA, or the next gate.

### Chat panel

**Approved mockup artifact**

No separate approved chat mockup file is checked into the repository. The approved contract is documented as a header, recipient selector, conversation body, bottom composer, and send control.

**Live implementation capture**

![Chat panel live capture](../../docs/ui-review/screenshots/2026-09-12/modal-chat-panel.png)

This is the current evidence for the panel shape. The capture reports no observed recipient or conversation in that scope, so an empty recipient state is expected.

### Usage detail

**Approved mockup artifact**

No separate approved usage-modal mockup file is checked in. The console overview reference contains the TBR and usage graph direction.

**Live implementation capture**

![Usage modal live capture](../../docs/ui-review/screenshots/2026-09-12/modal-usage.png)

Usage is a separate surface from TBR. The modal provides 1d, 1w, and 1m views, settings for date range, measured versus projected usage, and the estimated exhaustion label. The older capture still shows unavailable account allowance where the provider did not return it.

### Onboarding

**Canonical approved artwork used by the implementation**

![Onboarding slide 1 artwork](../../console/static/swarm-guided-tour-slide1.png)

![Onboarding slide 3 role-group artwork](../../console/static/swarm-guided-tour-role-group.png)

![Onboarding slide 4 project-tool artwork](../../console/static/swarm-guided-tour-project-tool.png)

**Live slide 1 — welcome**

![Onboarding welcome](../../docs/ui-review/screenshots/2026-09-12/onboarding-01-welcome.png)

**Live slide 2 — coordination**

![Onboarding coordination](../../docs/ui-review/screenshots/2026-09-12/onboarding-02-coordination.png)

**Live slide 3 — roles**

![Onboarding roles](../../docs/ui-review/screenshots/2026-09-12/onboarding-03-roles.png)

**Live slide 4 — projects**

![Onboarding projects](../../docs/ui-review/screenshots/2026-09-12/onboarding-04-projects.png)

**Live slide 5 — configuration**

![Onboarding configuration](../../docs/ui-review/screenshots/2026-09-12/onboarding-05-configuration.png)

The five live slides use the same SWARM shell, typography, orange action, and progress treatment. Slides 1, 3, and 4 now point at the checked-in canonical artwork above. Slide-level visual acceptance remains separate from provider and telemetry proof.

**Fresh local captures from the running console**

![Current onboarding slide 1](../../docs/ui-review/screenshots/2026-09-12/onboarding-01-welcome.png)

![Current onboarding slide 2](../../docs/ui-review/screenshots/2026-09-12/onboarding-02-coordination.png)

![Current onboarding slide 3 with the approved role-group graphic](../../docs/ui-review/screenshots/2026-09-12/onboarding-03-roles.png)

![Current onboarding slide 4 with the approved project-tool graphic](../../docs/ui-review/screenshots/2026-09-12/onboarding-04-projects.png)

![Current onboarding slide 5](../../docs/ui-review/screenshots/2026-09-12/onboarding-05-configuration.png)

Slide 3 is no longer an empty or blocked asset state. The browser capture shows the approved Developer, Designer, Architect, and Reviewer artwork loaded from `/assets/swarm-guided-tour-role-group.png`.

## Visual parity result

The references and captures answer different questions. The reference is the intended contract; the live image proves what the local console rendered. Current status is:

| Surface | Result | Remaining gap |
| --- | --- | --- |
| Onboarding slide 1 | Implemented | Fresh capture now uses the approved slide 1 artwork |
| Onboarding slide 3 | Implemented | Approved role-group graphic is present and loaded |
| Onboarding slide 4 | Implemented | Fresh capture now uses the approved project-tool artwork |
| Settings | Partial | Shell is intentionally retained; card spacing and content remain denser than the standalone mockup |
| Agents, Roles, Review | Partial | Data-safe live views do not yet match the alternate full-screen mockups in markup density and art treatment |
| Overview and hierarchy | Partial | Canonical hierarchy is present, but project/task feeds still determine whether live rows are populated |

## Mobile comparisons, side by side

### Roles

<table>
  <tr>
    <th>Mockup / reference</th>
    <th>Live implementation capture</th>
  </tr>
  <tr>
    <td><img src="../../artifacts/hq-mockups-2026-09-13/roles-mobile-reference.png" alt="Roles mobile reference"></td>
    <td><img src="../../docs/ui-review/screenshots/2026-09-12/screen-roles-mobile.png" alt="Roles mobile live capture"></td>
  </tr>
</table>

The mobile reference and live capture keep role identity, the circular mascot, and the collapsed detail path readable without allowing the role description to push the card layout apart.

### Overview

<table>
  <tr>
    <th>Mockup / reference</th>
    <th>Live implementation capture</th>
  </tr>
  <tr>
    <td>No separate approved mobile overview mockup is checked in.</td>
    <td>The private mobile Overview capture is not retained publicly.</td>
  </tr>
</table>

No public mobile Overview capture remains. Responsive rendering and design approval require separate, privacy-reviewed evidence.

## Artifact gaps to close

- Add an approved chat-panel mockup if the panel receives another visual pass.
- Add an approved usage-detail mockup that clearly separates TBR from usage and shows the full graph, 1d/1w/1m defaults, and date settings.
- Add mobile references for Overview, Review, Assets, Diagnostics, Settings, and Project detail if those responsive layouts need pixel-level acceptance.
- Capture a fresh desktop live set after the next UI build so historical 2026-09-12 screenshots do not remain the only implementation evidence for older surfaces.

## Evidence boundary

These images prove file-backed visual references and rendered local UI states. They do not prove that ChatGPT relay writes, Usage Saver routing, Codex limits, external provider authentication, or accepted hierarchy telemetry are currently working. Those claims require their own fresh receipts.
