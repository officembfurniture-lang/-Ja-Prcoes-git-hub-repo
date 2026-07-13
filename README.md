# HORYZONT P-0003 — Grid-Flexible Workload Passport

This public probe compares a baseline workload schedule with a grid-aware schedule while preserving declared service windows and site capacity.

It is a probe of **IMPERIUM ANIMUS — HORYZONT**, not the center of that system. Its purpose is to create a short, falsifiable path from a real workload trace to independently measurable operational evidence.

## Use

```yaml
name: Analyze workload flexibility
on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - id: flex
        uses: officembfurniture-lang/-Ja-Prcoes-git-hub-repo@main
        with:
          workload: examples/workload.json
          output: grid-flex-result.json
      - run: echo "Result ${{ steps.flex.outputs.result-hash }}"
```

For reproducible use, replace `main` with an immutable commit SHA.

## Evidence boundary

- this public repository and an immutable commit are distribution;
- an owner-controlled self-test is validation, not external use;
- a run in an independently controlled repository, bound to its run URL, input provenance and result hash, is an external-use candidate;
- metered operation proving that a workload was physically shifted without violating service constraints is a separate outcome candidate;
- a contribution or payment is capture only when independently visible;
- return exists only when the captured value reaches an operator-controlled rail.

The scheduler emits a plan. It never claims physical energy, emissions or financial savings by itself.

## Value exchange after evidence

An optional public DOT return rail is recorded in `value-exchange.json`. It was already published by an earlier HORYZONT probe. The repository does not prove control of the address, does not request payment before a verified outcome and reports capture and return as zero until an on-chain receipt is independently observed.

No open-source license or commercial license is granted by this research publication. Reuse beyond GitHub's platform permissions requires a separate license decision.
