# HORYZONT P-0004 — Outcome Mandate Protocol

P-0004 freezes a caller-provided task, budget ceiling, outcome criteria, evidence policy, kill gate and expiry into a deterministic mandate hash. The package does not sign an identity, authorize payment, execute a task or establish that later evidence is truthful.

## Intended immutable use

```yaml
- id: mandate
  uses: officembfurniture-lang/-Ja-Prcoes-git-hub-repo/p0004@<immutable-commit>
  with:
    draft: outcome-mandate-draft.json
    output: outcome-mandate.json
- run: echo "${{ steps.mandate.outputs.mandate-hash }}"
```

The caller controls the draft and retains responsibility for authority, provenance and every downstream action. The emitted `mandate-hash` binds the exact frozen content; it is not a signature or evidence that the task was executed.

## Evidence boundary

- this local adapter is an artifact, not distribution;
- a later immutable public package can establish distribution only after separate byte readback;
- a successful run in a non-owner repository is only an external-use candidate when pinned to the immutable package and bound to the caller draft plus emitted mandate hash;
- an attestation is only an outcome candidate after separate verification of its source and semantics;
- payment, trading and automatic economic execution remain disabled because A3 is inactive;
- capture and return require separately accepted evidence.

An owner-controlled self-test never qualifies as external use. No open-source or commercial license is granted by this research package.

