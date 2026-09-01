# VALUE_ENGINE v2

A generalized external-value execution engine. `BOUNTY_ENGINE_v1` remains as historical evidence and a narrow adapter; it is not the system boundary.

## State machine

`IDLE → SENSE → VERIFY → ROUTE → SELECT → ACQUIRE → PRODUCE → VALIDATE → DELIVER → OBSERVE → SETTLE → LEARN → IDLE`

Special state: `HUMAN_GATE` only when one bounded authorization/setup action unlocks continued autonomous execution.

## The critical ordering

`ROUTE` occurs before `SELECT/PRODUCE`. No work is started unless both a delivery route and a settlement route are known. This prevents producing valuable artifacts that cannot be submitted or monetized.

## Open-domain rule

The engine is not tied to GitHub, coding, bounties, waste, logistics, defence, or any other industry. It searches for externally verifiable demand that can be satisfied with currently available capabilities. Source adapters, deliverable types, and execution routes are replaceable.

Examples include funded digital tasks, agent-native jobs, contests/prizes, grants/challenges, research/data work, licensed digital artifacts, and authorized cost savings. A future opportunity class may be added when it creates a materially different route to realized value.

## Scheduler hierarchy

1. **GitHub Actions sensor** — deterministic hourly SENSE loop, persistent state, public-data collection. It remains available even if ChatGPT task slots are exhausted.
2. **Semantic worker** — ChatGPT/runtime cycle performs VERIFY, capability discovery, ROUTE, execution, and external observation using whatever authorized tools/connectors exist at runtime.
3. **Event validation** — GitHub Actions validates exact revisions on PR/push events.
4. **Manual workflow dispatch** — recovery path if scheduled execution is delayed or disabled.

The layers are deliberately heterogeneous so one scheduler/tool failure cannot silently become system failure.

## Runtime semantic-worker contract

On each semantic invocation:

1. Read `state.json`, `policy.json`, `routes.json`, `sources.json`, recent `observations.ndjson`, and `run-ledger.ndjson` if present.
2. Respect an unexpired lease. Never start a second active opportunity concurrently.
3. Rediscover current tool/connector capabilities rather than assuming yesterday's capabilities still exist.
4. VERIFY promising observations using primary sources. Separate advertised reward from externally verifiable funding/demand.
5. Build all currently executable delivery + settlement route pairs. Try authorized fallbacks before `ROUTE_BLOCKED`.
6. Select at most one opportunity. No route pair means no execution.
7. Produce the smallest complete artifact satisfying objective acceptance criteria.
8. Require independent validation evidence for the exact artifact revision. For GitHub code paths, query workflow runs for the head SHA; do not rely only on combined commit status.
9. Deliver only through the opportunity's native/authorized route. Do not create unsolicited outreach as a substitute for a missing submission route.
10. Observe review/acceptance and repair concrete failures while the opportunity remains economically rational.
11. Record `PAID` only from external settlement evidence. Merge/acceptance is not payment.
12. Learn only from externally observed outcomes and persist the changed decision policy.

## Fallback logic

Preferred route unavailable does not immediately kill an opportunity:

- native platform API/connector
- direct repository/account write when authorized
- existing cross-repository contribution path
- one-time `HUMAN_GATE` (fork, account authorization, payout setup, secret configuration)
- `ROUTE_BLOCKED` without wasting production compute

A blocked opportunity may remain observed and become executable later if a new connector, API, platform adapter, or authorization appears.

## Value accounting

`OBSERVED != VERIFIED != SELECTED != PRODUCED != DELIVERED != ACCEPTED != PAID`

Potential and advertised values are never added to realized value. Cash realization requires amount, currency, receipt/evidence and receipt timestamp. Non-cash value and cost savings are tracked separately rather than silently converted into money.

## Concurrency and crash recovery

Every active cycle holds a lease (`cycle_id`, owner, acquired/expires timestamps). A live lease causes a second scheduler to exit. Only an expired lease may be taken over. This allows redundant schedulers without duplicate work.

## Known connector-specific repair

The tested GitHub connector can branch, commit, open non-draft PRs, comment and merge in repositories with write access. It currently exposes no fork action, and its draft→ready mutation failed during testing. Therefore automated GitHub delivery creates non-draft PRs only after validation readiness and uses alternative routes or a bounded human gate for external forks.
