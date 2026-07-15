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

## Portfolio probe P-0005 — Preregistered Measurement Compiler

P-0005 freezes a bounded measurement draft into a deterministic, hash-addressed protocol. It does not execute an experiment or establish causality.

```yaml
- id: protocol
  uses: officembfurniture-lang/-Ja-Prcoes-git-hub-repo/p0005@62feb7ce4190989634b5f0da37f4bc4cc82a18ed
  with:
    draft: measurement-draft.json
    output: measurement-protocol.json
```

See [p0005/README.md](p0005/README.md) and [p0005/value-circuit.json](p0005/value-circuit.json). This immutable publication is distribution only. A non-owner successful workflow run bound to input provenance and the emitted protocol hash is only an external-use candidate; independently collected measurements bound to the same hash are a separate outcome candidate.

## Portfolio probe P-0006 — Material Lineage Opportunity Map

P-0006 deterministically joins caller-provided material-source and demand records. It emits coordination candidates without claiming physical transfer, ownership, compliance or savings.

```yaml
- id: lineage
  uses: officembfurniture-lang/-Ja-Prcoes-git-hub-repo/p0006@32773ad94fcd70bb8251a9f1d6d8cdb450e40151
  with:
    dataset: material-lineage.json
    output: material-lineage-opportunity-map.json
```

See [p0006/README.md](p0006/README.md) and [p0006/value-circuit.json](p0006/value-circuit.json). This immutable package is distribution only. A successful non-owner run bound to immutable code, input provenance and the deterministic result hash is only an external-use candidate; physical transfer, verified benefit, capture and return remain separate evidence gates.

## Portfolio probe P-0007 — Bounded Early-Action Backtest

P-0007 applies a frozen warning policy to caller-provided historical or synthetic episodes. It emits deterministic counterfactual comparisons without issuing warnings, authorizing action, or claiming avoided loss.

```yaml
- id: backtest
  uses: officembfurniture-lang/-Ja-Prcoes-git-hub-repo/p0007@458af9cb64fb2b550d1da1dc7597c935c48ed0de
  with:
    dataset: early-action-episodes.json
    output: early-action-backtest.json
```

See [p0007/README.md](p0007/README.md) and [p0007/value-circuit.json](p0007/value-circuit.json). This immutable package is distribution only. A successful non-owner run bound to immutable code, input provenance and the deterministic result hash is only an external-use candidate; observed outcome, capture and return remain separate evidence gates.
