# Repository Integrity Audit — 2026-10-09

Status: **HISTORICAL VALIDATION SNAPSHOT — NOT A LIVE HEALTH ATTESTATION**  
Scope: default branch, workflow topology, VALUE_ENGINE and BOUNTY_ENGINE state/ledgers, public probes P-0002 through P-0007, immutable distribution references, open PR/issues, and all repository branches compared with `main`.

This report records repository evidence. It is not an external-use, economic-return, consciousness, autonomy, or independent-outcome claim.

## Snapshot boundary and current-state readback

This document records evidence from the audit's original run. The claim that cycle 223 was current was accurate only at the earlier audit readback; it is **not** a live-cycle claim. A separate direct read of `value-engine/state.json` on 2026-10-09 observed `cycle = 227`, `counters.observed = 9455`, `counters.accepted = 2`, `counters.paid = 0`, `realized.cash = []`, and last sensor cycle `cycle-227-37965573990` at `2026-10-09T17:20:43Z`. These fields were read from the versioned repository file, **not independently revalidated against the run ledger or external settlement**. The cycle-223 ledger/observation reconciliation below is historical evidence and must not be projected onto cycle 227. No promotion or external outcome follows from the changed counter.

A future audit must date-stamp its source commit and re-run the ledger reconciliation before asserting consistency at a newer cycle. This correction changes the report's epistemic status only: no engine state, protected gate, receipt, route, branch, or external action was changed.

## Confirmed state (original audit snapshot)

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

GitHub Actions `Repository Integrity` run `37956173127` completed successfully on the pull-request merge ref containing the repository-wide gate and the initial form of this report.

Observed checks in that run:

- strict parse: 23 JSON files and 4 NDJSON files;
- in-memory syntax validation: 19 Python files;
- BOUNTY_ENGINE validator: OK;
- VALUE_ENGINE invariants: OK;
- VALUE_ENGINE suite: 69 tests passed;
- repository-wide regression suite: 13 tests passed;
- P-0002 through P-0007 self-tests: success;
- portfolio truth-boundary enforcement: OK;
- repository remained unmodified by self-tests.

Because this status update changes the PR head, the final head must also receive a successful `Repository Integrity` run before merge. A failure must be preserved and repaired causally; acceptance criteria must not be weakened merely to obtain a green run.
