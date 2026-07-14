# P-0005 — reusable Preregistered Measurement Compiler action

Status: approved for additive publication under `p0005/` in the existing HORYZONT public action repository. Publication and immutable readback remain distribution only.

A non-person-directed caller can use the package as follows:

```yaml
name: Freeze measurement protocol
on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  compile:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - id: protocol
        uses: officembfurniture-lang/-Ja-Prcoes-git-hub-repo/p0005@main
        with:
          draft: measurement-draft.json
          output: measurement-protocol.json
      - run: echo "Protocol ${{ steps.protocol.outputs.protocol-hash }}"
```

Replace `main` with the immutable commit recorded in `value-circuit.json` before reproducible use.

The action has no network step and does not upload the input or output. It validates the draft, freezes the design and returns the protocol hash plus a review flag. It does not recruit participants, execute an experiment, collect measurements, establish causality or authorize work involving people, living systems, hazardous materials or critical infrastructure.

Evidence remains layered:

- a public immutable release is `distribution`, not use;
- a successful workflow in a repository outside the HORYZONT owner's control, bound to its run URL and emitted protocol hash, is only a candidate for `external_use`;
- a self-test or owner-controlled workflow never qualifies as external use;
- independently collected measurements bound to the same hash are a separate `outcome_candidate` and require verification.

No person-directed outreach is part of this channel. No open-source or commercial license is granted by this publication; the action only exposes a falsifiable technical probe within the permissions of the hosting platform.
