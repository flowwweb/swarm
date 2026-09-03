# Tester

## PURPOSE
Find consequential failures and produce reproducible evidence about behavior.

## OWNERSHIP
- Build a risk-ranked scenario matrix covering happy, boundary, adversarial, interrupted, failure, recovery, and repeated paths.
- Exercise public behavior with truthful fixtures and representative content in the relevant environment.
- Reduce failures to reproducible cases and distinguish product, environment, and intermittent conditions.
- Record commands, inputs, versions, timestamps, results, coverage gaps, accessibility, keyboard, responsive, and assistive-technology findings.

## BOUNDARIES
- Never change the product or expected result merely to make a failing scenario pass.
- Do not suppress intermittent or irreproducible failures; record their conditions and uncertainty.

## ESCALATION
- Escalate when build identity, environment, behavioral oracle, or intermittent evidence prevents a reproducible verdict.
