# P-0002 — reusable Agent Operations Passport action

Status: bounded publication package for additive path `p0002` in the named A2 GitHub scope. Distribution exists only after immutable byte readback, a discovery route pinned to the package commit and separately verified distribution evidence.

After immutable publication, a separate repository can call it as follows:

```yaml
name: Agent operations passport
on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  passport:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - id: passport
        uses: officembfurniture-lang/-Ja-Prcoes-git-hub-repo/p0002@<immutable-commit>
      - run: echo "${{ steps.passport.outputs.inventory-hash }}"
```

The action exports hashes, paths, sizes and filename-derived categories. It skips common secret filenames and never exports source contents. `inventory-hash` excludes `generated_at`, so identical repository bytes have a deterministic identity; `passport-hash` identifies the complete timestamped report. Neither is legal advice or a conformity assessment.

An external workflow run qualifies as candidate `external_use` only if the caller repository is not controlled by the HORYZONT owner. A run in the publication repository is a self-test, not external use. No open-source or commercial license is granted by this research publication.
