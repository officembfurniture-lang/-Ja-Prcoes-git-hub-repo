# HORYZONT P-0007 — Bounded Early-Action Backtest

P-0007 applies a frozen warning policy to caller-provided historical or synthetic episodes. It emits a deterministic counterfactual comparison; it does not issue warnings, authorize action, establish avoided loss, or claim operational effectiveness.

## Use

```yaml
- id: backtest
  uses: officembfurniture-lang/-Ja-Prcoes-git-hub-repo/p0007@<immutable-commit>
  with:
    dataset: early-action-episodes.json
    output: early-action-backtest.json
- run: echo "${{ steps.backtest.outputs.result-hash }}"
```

The caller supplies the dataset and remains responsible for its provenance. The action emits `result-hash` and `episode-count` so a public run can be bound to an exact deterministic result.

## Evidence boundary

- this immutable package is distribution only;
- a successful run in a non-owner repository is an external-use candidate only when pinned to the package commit and bound to a provenance-bearing input trace plus the emitted result hash;
- an avoided-loss or operational-effectiveness claim requires independent attestation against observed outcomes;
- capture requires a separately evidenced resilience-analysis contract, invoice, or other authorized rail;
- return exists only when captured value reaches an operator-controlled rail.

No open-source or commercial license is granted by this research publication.

