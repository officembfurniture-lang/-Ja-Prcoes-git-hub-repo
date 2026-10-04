# Evidence Lineage Independence — HOLD experiment

This experiment operationalizes one narrow correction:

> external control is not the same thing as epistemic independence.

The current HORYZONT evidence gates correctly distinguish owner-controlled
validation from external use, but an external evaluator can still share a
source, model family, dataset lineage, prompt lineage, or toolchain with another
evaluator. Counting those outputs as independent can manufacture confidence.

`audit.py` therefore does **not** score truth and never emits
`independence_verified=true`. It only detects declared common causes and
prevents a weak inference:

`different operator => independent evidence`.

Statuses:

- `CORRELATED_DECLARED_LINEAGE` — at least one pair shares a declared lineage;
- `UNRESOLVED` — required lineage information is missing;
- `DISTINCT_DECLARED_LINEAGE` — declarations differ, but independence and truth
  remain unverified.

This branch is a HOLD experiment. It changes no VALUE_ENGINE state, routes,
outcomes, capture, settlement, permissions, or promotion rules. No result from
this experiment is a verified external outcome.

## Run

```bash
python experiments/evidence-lineage-independence/audit.py evidence.json
python -m unittest experiments/evidence-lineage-independence/test_audit.py
```

The intended next falsification step is to apply the audit to evidence that looks
independent by ownership but is known to share a hidden common cause, and verify
that the old gate would overcount it while this audit refuses the inference.
