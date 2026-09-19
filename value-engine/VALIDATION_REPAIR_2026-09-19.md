# VALUE_ENGINE gate repair — 19 September 2026

The validator still accepted three invalid production-state families diagnosed
on 8 September: no active opportunity, explicitly false verification gates,
and route identifiers absent from the registry. Its SHA-256 was still
`b141afcc5db2b707477a825b23ef4fb79f183da02f670775d43503518e106c40`.
This completes that earlier repair; it is not a new discovery.

## Change

The existing validator now requires a named active opportunity, a complete,
well-formed lease, and six literal opportunity-specific verification flags
during PRODUCE, VALIDATE, DELIVER, OBSERVE and SETTLE. Both route identifiers
must exist and support the declared role. Policy flags alone cannot substitute
for completed opportunity verification.

It also rejects boolean counters, invalid cash amounts and receipt fields,
validates outcomes.ndjson, and binds the paid counter to distinct final PAID
opportunity receipts. Acceptance remains separate from payment.

Only validation code, tests, documentation and its CI workflow change. The
sensor, policy, routing registry, state, observations, run ledger and existing
outcomes retain their bytes. No controller, lease acquisition, opportunity
execution, permission expansion, outreach or transfer is introduced.

## Verification

Baseline commit: `a4e568bfc71412e69ac063dd33765b1102eaca36`.

| Prior diagnostic | Original validator | Repaired validator |
|---|---|---|
| Actual persisted IDLE state | accepts | accepts |
| Production without active opportunity | incorrectly accepts | rejects |
| Production with explicitly false gates | incorrectly accepts | rejects |
| Production with unknown route identifiers | incorrectly accepts | rejects |
| Negative-counter control | rejects | rejects |

The exact earlier examples with false gates and unknown routes also lack a
lease, so the repaired validator rejects those examples at the lease check.
Separate regression subcases supply a valid lease and isolate each false gate
and each invalid route; these are rejected at their respective checks.

- 24 validator test methods pass, including isolated synthetic subcases.
- The current branch's full VALUE_ENGINE suite passes 32 tests.
- The same 24 validator test methods run against the unchanged original code
  produce 78 subcase failures and 9 errors. These are not 87 independent bugs.
- Combined with the immutable triage fix from PR #12,
  `58129ef3489a30b8f506de65846091d65cf25936`, all 48 tests pass.
- VALUE_ENGINE state validation, BOUNTY_ENGINE validation, compileall and
  whitespace checks pass.
- A scoped five-family secret-pattern scan of 56 files found no matches.
  This is not an exhaustive audit.
- SHA-256 comparison confirms state, observations, run ledger and outcomes
  remained unchanged during local validation.

Machine-readable local results:
[validation-repair-evidence-2026-09-19.json](validation-repair-evidence-2026-09-19.json).

## Operational limits and next gates

Validation checks structure and declared flags. It does not authenticate source
documents or payment references, prove control of a destination, or observe a
wallet balance. The semantic worker must verify actual evidence before setting
flags or recording receipts. A fixture payment reference is deliberately used
in one positive test; passing that test is not a payment.

Valid historical leases can be audited even after expiry. A worker must still
check current lease ownership and expiry before executing anything.

The repair is compatible with today's IDLE sensor snapshot (cycle 114):
4,848 observations, two accepted outcomes, zero paid outcomes. More observations
do not constitute more deliveries. The two accepted outcomes and their amounts
are not re-awarded or promoted by this change.

Omega PR #1 remains a separate HOLD experiment under Issue #2. These validator
regressions are not its required paired held-out trial and do not measure
Mateusz's correction burden. Canonical archive access also remains a separate
blocked dependency; this repair does not claim canonical chain verification.

After integration, the existing validation workflow runs the complete
VALUE_ENGINE test suite before accepting future changes. The next economic
step is source verification plus an executable delivery/settlement route, or
observation of actual settlement evidence for the existing accepted outcomes.
