# HORYZONT P-0006 — Material Lineage Opportunity Map

P-0006 joins caller-provided material source records to compatible demand records using declared material codes, mass, quality tags, contaminants and regions. It emits deterministic coordination candidates; it does not verify physical material, ownership, logistics, compliance, savings or transfer.

## Use

```yaml
- id: lineage
  uses: officembfurniture-lang/-Ja-Prcoes-git-hub-repo/p0006@<immutable-commit>
  with:
    dataset: material-lineage.json
    output: material-lineage-opportunity-map.json
- run: echo "${{ steps.lineage.outputs.result-hash }}"
```

The caller supplies the dataset and retains responsibility for its provenance. The action emits `result-hash` and `candidate-count` so a public run can be bound to an exact deterministic result.

## Evidence boundary

- this immutable package is distribution only;
- a successful run in a non-owner repository is an external-use candidate only when it is pinned to the package commit and bound to a provenance-bearing input trace plus the emitted result hash;
- a candidate match becomes an outcome candidate only after independent holder and receiver verification;
- capture requires a separately evidenced license, invoice or share of verified savings;
- return exists only when captured value reaches an operator-controlled rail.

No open-source or commercial license is granted by this research publication.
