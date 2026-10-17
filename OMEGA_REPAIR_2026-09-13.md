# Omega: complete the previously specified repair

The earlier repair specification described strict input and evidence checks, but the experimental branch still ran the permissive implementation at `effec24d744d6cb0b899eed10031e97d9c0eb82e`. This change implements that outstanding repair in the existing `omega_shadow_driver_v0.py` entry point. It adds no parallel driver and changes no production workflow or authority.

The recovered specification is dated 23 August 2026; its recovered text SHA-256 is `2eeb01b825f8162e9ba2cc501d590d94c34d52dbb31257b8cd4535166d949285`. The original standalone v1 source and fixtures were not available. This is a new implementation from that specification and the current branch, not a claim of an exact source-code port or a new discovery of the known defects.

## What now changes decisions

| Known failure | Previous result in reproduction | Repaired result |
|---|---|---|
| Nonempty prose used as provenance | PROMOTE | INPUT_INVALID |
| Progress claim cites nonexistent evidence | PROMOTE | DRIVER_REGRESSION |
| Null human-burden reading treated as zero | PROMOTE | INPUT_INVALID |
| NaN debt bypasses the limit | PROMOTE | INPUT_INVALID |
| Human burden increases despite a material effect | PROMOTE | DRIVER_REGRESSION |

Evidence IDs must be nonblank and unique. Progress claims, actions and material effects must reference the verified evidence set. An executed action with missing readback or unresolved references stays HOLD. Unknown burden remains `null`; it does not become zero. Explicitly measured burden requires two finite, nonnegative numeric readings. Booleans, numeric strings, nulls, invalid limits, non-finite totals and non-JSON state are rejected without emitting non-finite output.

The human-burden regression check now applies even when a material effect is reported. This enforces the existing [Issue #2 criterion](https://github.com/officembfurniture-lang/-Ja-Prcoes-git-hub-repo/issues/2); it does not relax the promotion standard.

## Provenance contract and its limit

Every verified evidence/action/effect claim needs an object with an allowlisted `kind`, nonempty `locator`, and a boolean `readback_verified`. Only a true readback flag can support a verified claim.

| Kind | Intended source | What still needs independent verification |
|---|---|---|
| `source_document` | Official source snapshot or document | Authentic source, relevant passage and exact revision |
| `artifact_readback` | Compared file or artifact bytes | Actual byte comparison, expected artifact and revision |
| `test_run` | Test execution receipt | Run identity, tested revision and observed test result |
| `paired_comparison` | Same-input baseline versus candidate comparison | Frozen inputs, comparable measurements and effect attribution |

These four kinds cover the current intended inputs. They are schema categories, not an authenticity oracle. The pure evaluator does not fetch locators, compare remote bytes, authenticate a source or verify that its content supports the claim. Its caller must establish those facts before marking a receipt verified. Unrecognized provenance kinds require an explicit contract review; a free-form claim must not be silently upgraded to an accepted kind.

Old records with string provenance or implicit human-burden measurements no longer satisfy the input contract. Their producers need explicit migration supported by actual receipts. `omega_shadow_fixtures_v0.json` and the historical P-0003 result are preserved byte-for-byte. New synthetic fixtures are separate in `omega_shadow_fixtures_v1.json`; their `fixture://` locators and burden values are test data only.

## Validation

- Python 3.12: 21 unit tests passed, including a 12-case fixture suite and malformed-input subcases.
- Five known failure classes were reproduced against the unchanged old source, then evaluated against the repaired source. All five old PROMOTE results are rejected by the appropriate repaired gate.
- The 12 same-input regression cases have 7 unchanged verdicts and 5 repaired verdicts. These were selected for regression testing; they are not held-out evidence of live performance.
- `compileall`, fixture JSON validation and whitespace checks passed.
- A six-family pattern scan of the branch and proposed files found no secrets. This is a scoped pattern scan, not an exhaustive audit.
- The existing Python 3.12 workflow now includes the new fixture and result/report dependencies in its path filter, and validates compilation and fixture JSON.

Machine-readable local evidence is in `omega_repair_evidence_2026-09-13.json`. Remote CI and exact branch readback are reported separately in PR #1 only after they have actually completed.

## Remaining discriminating test

The experiment decision remains **HOLD**. A fixture returning PROMOTE is a classifier test, not authorization to merge or deploy the experiment.

Before promotion, freeze the current baseline and candidate revisions and select the same new held-out inputs for both. Capture the corresponding source/action receipts; measure corrections and restoration burden without filling absent readings. Compare unsupported progress claims, provenance and readback failures, decision-changing effects and human correction burden. Do not tune either path after observing these outcomes. A tie stays HOLD; any increase in unsupported claims or correction burden is DRIVER_REGRESSION.

No live paired trial or real before/after human-burden measurement was performed by this repair. It does not establish payment, economic return, reduced user workload, resident execution, or consciousness. Issue #2 stays open and PR #1 remains unmerged.
