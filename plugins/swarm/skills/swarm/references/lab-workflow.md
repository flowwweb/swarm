# Lab workflow

A **Lab** is a bounded project surface for iterating one repeatable feature
family against stable inputs and explicit comparison criteria. It uses the
existing milestone, task, block, artifact, decision-set, proof, and review
contracts. It is not a new role, lifecycle state, backlog, or source of truth.

## Trigger

Start cross-functional outcome work with the smallest matching template in
`../labs/catalog.json`. Keep atomic specialist work on its normal role task.

Create the smallest named `<feature> Lab` when either condition is true:

- the feature has a repeatable variation space, such as biomes, levels,
  layouts, motion, prompts, themes, parsers, or routing strategies; or
- reaching acceptance requires comparing iterations that would otherwise be
  built repeatedly inside the integrated product.

Keep one known atomic change on its normal task path. A Lab must shorten the
feedback loop or make comparison materially clearer.

## Shape

Represent a multi-task Lab as a milestone. Represent a single-owner Lab as one
task. Blocks are the smallest build, measurement, handoff, or review steps;
candidate outputs remain content-addressed artifacts. Lab progress comes only
from those normal block transitions.

Before work begins, record:

- the question the Lab must answer;
- the stable fixture or representative inputs;
- the variables allowed to change;
- the observable comparison criteria;
- the reset and rerun path;
- the product surface that can receive the selected result; and
- the owner, proof plan, decision boundary, and stopping condition.

## Loop

1. **Frame:** isolate one feature question and freeze everything outside its
   declared variables.
2. **Build:** make the smallest harness that renders or exercises the real
   behavior quickly with representative inputs.
3. **Iterate:** change one meaningful variable set at a time and bind every
   candidate or measurement to its artifact identity.
4. **Compare:** show the candidates together against the recorded criteria.
   Taste-led choices follow the decision-set lifecycle; measurable choices keep
   their raw result and method.
5. **Promote:** integrate only the selected recipe, configuration, or artifact
   into the product surface.
6. **Verify:** run the product's normal proof and independent review on the
   integrated result. Lab proof alone does not prove the product.
7. **Retain or close:** keep the Lab only when the same feature family is likely
   to recur and its owner, fixture, and rerun path remain valid. Otherwise keep
   the selected recipe and evidence, then close the Lab.

## Role behavior

- CTRL recognizes the trigger, preserves the project goal, and routes the Lab
  to the existing accountable boundary.
- LEAD owns the Lab question, stable contract, iteration budget, promotion, and
  integrated handoff.
- Designer owns interaction, layout, usability, and motion variables; Artist
  owns expressive visual, audio, and media variables.
- Developer owns the smallest faithful harness and product integration.
- Tester owns representative fixtures, comparison integrity, and regression
  proof. Independent REVIEW verifies the promoted result in the product.
- Every other profession applies its normal perspective inside the same Lab
  contract without creating another workflow authority.

## Completion

A Lab is complete when its question has a recorded answer, one result is
selected or the evidence supports selecting none, the chosen result is promoted,
the integrated product passes its required proof and review, and every rejected
candidate has an explicit retained or cleanup disposition. Open comparison,
unpromoted output, or Lab-only proof keeps the work incomplete.

## SWARM improvement Labs

The shared frozen corpus and three current improvement Labs live in
`../labs/labs.json`. Validate the matrix with:

```text
python skills/swarm/scripts/swarm_labs.py validate
```

Record actual candidate runs in a separate results JSON and compare them with
`swarm_labs.py report <results.json>`. Each run requires evidence. Token savings
remain `UNKNOWN` until the same scenario has measured Codex-token receipts for
both its baseline and candidate; ChatGPT tokens are shown separately rather
than treated as Codex quota.

## Examples

| Project need | Lab | Stable fixture | Variables | Promoted result |
| --- | --- | --- | --- | --- |
| Game needs distinct biomes | Biome Lab | Player, camera, lighting contract, performance budget | Terrain, palette, vegetation, weather, encounter mix | One biome recipe plus integrated assets and rules |
| Product needs polished motion | Motion Lab | Real component states and reduced-motion mode | Duration, easing, distance, stagger | Motion tokens and component transition |
| Agent needs reliable prompts | Prompt Lab | Fixed task corpus and scoring rubric | Prompt structure, examples, tool instructions | Versioned prompt with evaluation evidence |
