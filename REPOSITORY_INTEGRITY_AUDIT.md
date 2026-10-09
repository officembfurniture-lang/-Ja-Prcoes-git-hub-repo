# Repository Integrity Audit — 2026-10-09

Status: **VALIDATION_PENDING**  
Scope: default branch, workflow topology, VALUE_ENGINE and BOUNTY_ENGINE state/ledgers, public probes P-0002 through P-0007, immutable distribution references, open PR/issues, and all repository branches compared with `main`.

This report records repository evidence. It is not an external-use, economic-return, consciousness, autonomy, or independent-outcome claim.

## Confirmed state

- VALUE_ENGINE cycle 223 completed on GitHub-hosted Actions with zero source errors.
- The cycle ran 65 VALUE_ENGINE regression tests successfully before persistence.
- The persisted cycle changed only `value-engine/state.json`, `value-engine/observations.ndjson`, and `value-engine/run-ledger.ndjson`.
- `state.cycle = 223`; the run ledger contains 223 valid records; the sum of ledger `new_observations` is 9323; the observation store contains 9323 valid NDJSON records.
- All 9323 observations remain `OBSERVED`, with `primary_source_verified=false`, `realized_value=0`, and no delivery or settlement route attached.
- VALUE_ENGINE records two ACCEPTED outcomes and zero PAID outcomes. Acceptance is not treated as payment.
- The immutable package refs recorded for P-0002 through P-0007 resolve on GitHub. Their value-circuit files do not claim verified external use, outcome, capture, or return.

## Repairs applied during this audit

- Added a repository-wide read-only integrity workflow covering JSON/NDJSON parsing, Python syntax, both engines, VALUE_ENGINE regressions, public probe self-tests, truth boundaries, and repository mutation checks.
- Made repository JSON/NDJSON parsing reject non-finite constants.
- Added repository-wide regression tests for public probe input boundaries.
- Hardened P-0002 against symlink escape from the declared scan root.
- Hardened P-0003/P-0004/P-0005/P-0006/P-0007 against unsafe type coercion and non-finite numeric input.
- Fixed P-0006 region eligibility and duplicate aggregate mass. The demonstration now distinguishes unique candidate source mass from pairwise candidate mass.
- Hardened BOUNTY_ENGINE validation and added regression tests.
- Pinned executing GitHub Actions dependencies to immutable commit SHAs.
- Replaced moving or placeholder action references in public documentation with the recorded immutable package revisions.
- Kept the Ω shadow-driver experiment on HOLD; no synthetic result is promoted into live evidence.

## Branch and experiment boundary

The repository contains historical delivery, repair, experiment, policy, and engine branches. Several are far behind `main`; some contain branch-only evidence. They are retained as provenance and are **not** interpreted as active production state merely because the branch exists.

The evidence-lineage-independence branch remains an experiment. PR #1 / Issue #2 remain HOLD pending the required paired held-out validation and actual human-correction-burden evidence.

## External validation boundary

GitHub-hosted CI is an external execution environment relative to the local code path, but an owner-controlled repository run is **not independent external use** under this repository's own evidence contract. Independent use/outcome/capture/return remain false unless separately evidenced.

## Merge gate for this audit

This audit may change to **VALIDATED** only after the `Repository Integrity` workflow succeeds on the pull-request merge ref containing this report and the current audit gate. A failure must be preserved and repaired causally; the acceptance criteria must not be weakened merely to obtain a green run.
