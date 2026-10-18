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

## Source-snapshot refresh semantics

The sensor fingerprints GitHub issues by source identity, URL and source update time.
A previously captured revision can remain open without receiving a new `updated_at`.
After six days, a fresh successful GitHub search readback of that revision is stored
as a new **snapshot** (the fingerprint remains unchanged but `detected_at` advances).
This keeps it eligible for the separate seven-day pre-VERIFY snapshot freshness
gate without bypassing that gate. No network result means no refresh.

`last_cycle_result.new_observations` counts previously unseen source revisions;
`last_cycle_result.refreshed_snapshots` counts repeated source-revision readbacks.
`counters.observed` counts appended records from both groups, **not** unique
opportunities, verified demand, funding, customer commitments or financial value.
Multiple search queries cannot duplicate a fingerprint within a single run.
Every queue candidate still requires independent primary-source verification
before any selection or work.

## Bounded historical source readback

Discovery searches return only ten results per query. An older issue can be
absent from these results even while it remains open. For stored sources whose
snapshot is already stale and whose conservative triage status would otherwise
be `HOLD_STALE_OBSERVATION`, the sensor may attempt at most **three direct,
read-only GitHub issue GETs per cycle**. These do not authorize outreach, a
claim, a deliverable or money movement.

Candidate URLs must match the public GitHub `/owner/repo/issues/number` form.
The live issue ID, URL and state must match the stored source, or the request
fails closed. A returned `closed` state is retained in the observation history
but routed to `HOLD_SOURCE_CLOSED` in triage. Network failures do not extend
freshness. Previously offered, unverified, prohibited or liability-gated work
does not become executable because of a successful GET.

Failures during bounded direct-readback attempts are retained in the
canonical run ledger, including HTTP status codes when available. A previously
failed issue URL receives a **24-hour retry cooldown**, so an inaccessible
source cannot repeatedly consume the same three-request budget every cycle.
A timeout, HTTP error or mismatched identity never renews observation freshness.
The cooldown expires automatically and is not evidence that a source is closed.

The run ledger separates `direct_readback_attempts`, `direct_readback_captures`
and `direct_readback_closed`. These are sensor measurements, not confirmed
payment or adoption. The cap and deterministic ranking prevent unbounded
retrieval, but do not guarantee that every archived issue is revisited.

## Full pre-VERIFY pool and bounded fair readback

On 2026-10-11, a real triage run identified 219 `QUEUE_VERIFY` source
candidates but its historical `--limit 50` only exposed the top 50 to
`source_probe.py`. No rotation inside the probe could ever inspect the 169
entries discarded by the preceding stage. This was a cross-stage reachability
defect, **not** a shortage of network requests.

The scheduled shadow job now uses `triage.py --limit 0` to pass its **entire
ranked pre-VERIFY pool** to the existing, independently capped readback module,
up to a strict finite artifact bound of 5000 candidates. If more than 5000
eligible items would be produced, triage fails closed instead of silently
omitting some candidates. Its summary records `complete_verify_queue`,
`verify_queue_total`, `verify_queue_emitted` and the cap. The workflow
requires exact agreement of queue count and candidate total.

The readback module still performs at most **three** public read-only GitHub
GETs per cycle, keeping the top-ranked source and deterministically rotating
the remaining two across the full emitted universe. For a fixed queue of 219
unique eligible URLs, 109 consecutive rotations reach all 219; this is an
offline regression test, not a claim of real-world coverage when sources
change, GitHub searches fail, or the queue grows. Original source funding,
approval, execution and payment remain unverified. No API write privileges,
contacts, fees or payment rails are added.

## Bounded source evidence, separate from triage rank

The `Value Engine Triage Shadow` workflow now executes `source_probe.py`
on up to **three unique pre-VERIFY queue URLs** per run. Its first
readback targets the highest-ranked eligible queue entry; the remaining
up to two URLs rotate deterministically using the GitHub workflow
`run_number`. This preserves priority while covering other candidates
without increasing the per-run request cap. The receipt records the
rotation and exact original queue ranks, so the selection can be replayed.
A repeated readback is not a new external outcome. Its GitHub API
`GET` receipts record whether an issue currently exists and is open or
closed, the original queued title/update timestamp, returned source
revision fields, a SHA-256 digest of selected returned source content,
and a time-bound provenance reference to the queue's SHA-256.

The probe deliberately does not trust the bounty label, a source's
self-asserted `funded` text or the triage score as proof of secured
payment. All resulting records and the summary preserve
`primary_source_verified=false`,
`demand_or_reward_verified=false`,
`settlement_route_verified=false`,
`authorization_to_execute=false` and `realized_value=0`.
Malformed URLs, pull-request API payloads, mismatched issue numbers and
HTTP errors yield no positive evidence. Network errors are auditable
`READBACK_FAILED` receipts, not a successful verification.

The readback receipts, input queue, SHA-256 manifest and checkout
revision are retained together in a seven-day workflow artifact.
A successful run verifies **the bounded data-acquisition mechanism**;
it does not show that an independently controlled actor accepted,
funded, bought, used, or paid for anything. Financial, delivery, safety
and consent gates remain separate prior to execution.

## Forward-only sensor archive content checkpoint

Starting with the first completed cycle running this code, the sensor records
the SHA-256 of the complete **byte content** of `observations.ndjson` in both
its state and completed-cycle ledger receipt. The validator checks actual bytes
against this matching pair; triage validates its pinned checkout before queueing
readback. Unlike row-count reconciliation alone, changing title, body, status,
or order without changing the number of lines then fails closed.

The checkpoint is **backward-compatible** with pre-feature cycles. It is a
content integrity proxy, NOT a digital signature, independently immutable
WORM archive, proof of authentic sources or economic value. A party able to
rewrite the archive and both receipts could forge a consistent new checkpoint.
Existing safety and external-verification rules remain unchanged.

## Three-way append-only sensor history integrity

Every VALUE_ENGINE validation now checks the three files as one accounting
boundary: `state.json`, `run-ledger.ndjson` and `observations.ndjson`.
All completed `SENSE_COMPLETE` ledger cycles must be sequential, with
non-negative integer new/refresh counts. Their combined appended count must
equal both the number of observation records **and** the state's
`counters.observed`. The most recent completed receipt must match the
state's cycle identifier, timestamp, new/refresh counts and error list.
A busy-lease receipt does not create or count an observation. Missing files,
truncated observations, duplicate entries, altered totals and reordered
completed cycles fail validation before sensor state persistence.

This proves **internal consistency**, not factual truth of third-party sources,
the identity of distinct offers, or payment. Observations may include repeated
readbacks of the same source revision. `counters.observed` is the number of
appended snapshots, not verified or uniquely funded opportunities.

## GitHub API network boundary and hostile-input tests

The public sensor and the downstream source readback must retain a strict
network origin boundary despite receiving URLs and content from third-party
GitHub issues. Authenticated urllib requests previously inherited Python's
default HTTP redirect handler, which copies the `Authorization` header onto
a redirected Request. An HTTP 30x Location to another host could therefore
carry the Actions token outside the intended API origin. This is a **code-level
risk**, not evidence that a credential was leaked in any actual run.

The sensor now uses an opener whose redirect handler accepts only canonical
`https://api.github.com` redirects. A redirect to HTTP, another host, an
alternate port, or an authority with embedded credentials raises an HTTP
error and records the fetch as unsuccessful. Existing bounded anonymous
fallback for 401/403 responses is preserved. Search results are filtered to
well-shaped, actual issue URLs with matching issue numbers, not GitHub pull
requests or arbitrary links. Existing data and verified outcomes are untouched.

Offline adversarial regressions test token-bearing cross-host 301/302/307
redirects, legitimate same-origin redirects, auth use by both fetch routes,
malformed search records, and continued capture of normal issue entries.
Passing these tests means that the new code rejects the simulated failure
modes; it does not prove immunity against all network or API compromise.

## Ω HOLD: experimental lane open, promotion still gated (2026-10-11)

Issue #2 governs promotion of the historical experimental Ω shadow driver
(PR #1). The workflow `Omega Paired Shadow Trial` now opens an ongoing
**read-only test lane** after successful sensor runs, plus PR/manual testing.
The driver revision is **pinned** to
`23019008e67b897a008ff786badf3aa976da84a5`, checked out independently.
The workflow resolves the exact originating sensor commit before reading
`state.json` and `observations.ndjson`, validates their SHA-256 binding,
and deterministically selects up to 16 distinct real unverified source
observations **before** computing the baseline/source classifier or Ω output.

Both evaluate the **same underlying records**, but different safeguards:
baseline triage marks source review/hold without granting authority, and Ω
checks that no unsupported material progress is promoted. The outputs
record false-promotion and evidence gates, sample identities, snapshot
revision, and whether real human correction burden was measured. This is a
narrow **same-input safety/compatibility check**, not a head-to-head
effectiveness comparison, since baseline and Ω do not currently optimize
the same outcome. It cannot prove Ω outperforms baseline. Consequently
`promotion_gate=HOLD` even after all tests pass. Repeated identical
no-delta reports are not evidence of accumulated improvement.

This creates a falsifiable, repeatable test path **without** enabling
payment, engagement, live task execution, self-modification, hidden code
promotion or merging PR #1/#26. Genuine promotion requires a further
held-out paired effectiveness trial on comparably defined outcomes,
independently verified material effects and measured human correction/
restoration burden. A tie or unknown burden remains HOLD. New unverified
sensor observations can never be silently represented as VERIFIED.

## Cross-run readback feedback with bounded retry cooldown (2026-10-11)

The next triage cycle previously received **no** prior source-readback decisions:
the highest-ranked GitHub issue could consume one of just three GETs again and
again, including after a recent direct source readback had already established
its state. In each run, the workflow now *optionally* downloads the artifact
from the most recent **successful main-branch `workflow_run` triage** via
read-only `actions:read`. PR-produced artifacts are excluded from feedback;
no external source is contacted by this retrieval.

`readback_cooldown.py` checks the prior queue bytes against the prior
source-probe summary SHA-256, bound original ranks/URLs/fingerprints, time,
zero authority flags and each GET receipt. Only a **matching unchanged source
revision** may be temporarily deferred: previously read OPEN sources for
at most 2 hours, CLOSED sources for at most 6 hours, and inaccessible
HTTP 403/404/410 sources for at most 2 hours. Remaining eligible sources
are considered at the existing max-three-GET budget. The receipt summary
reports original queue ranks skipped, previous observation class, effective
eligible count and whether optional feedback **actually changed candidate
selection**. `VALID_NO_SUPPRESSION` means the previous artifact was valid but
no source was deferred (for example, after its TTL expired); only
`SUPPRESSION_APPLIED` denotes a measured selection effect. Neither is proof
of financial value or external adoption.

These are **retry decisions, not persistent source-state claims**.
A 404 does not mean a source is closed; a previously closed issue may reopen;
and source content changing produces a new revision/fingerprint eligible
for immediate readback. Expired feedback causes fresh GETs again. Missing,
unusable, future-dated or unbound previous artifacts fall back to ordinary
current GET selection instead of blocking the pipeline or elevating authority.
All current readbacks remain non-authoritative. This is an evidence-based
bounded feedback mechanism, **not** self-modifying model parameters,
verification, new revenue, or permission for third-party engagement.

## Reusing bounded fresh source evidence without new API calls

The source readback `GET` already fetches the live GitHub issue title and
body but used to discard the body before `readback_review.py`. This froze
source-risk recognition: even when a changed issue now explicitly prohibited
starting work or required depositing funds, the downstream stage emitted only
`RE_TRIAGE_CHANGED_SOURCE` without using the available text.

The readback receipt now retains the current source title, at most the first
24,000 characters of its public body, and an explicit truncation flag. This
covers the current 11,961- and 18,371-character candidate bodies while keeping
a hard per-source artifact bound. Longer bodies remain explicitly truncated
and cannot be treated as risk-free. The source-readback receipt summary is now
schema v2: a prior v1 artifact is rejected as a cooldown hint and triggers fresh
bounded GETs, so an earlier 4,000-character truncated receipt cannot suppress
the first read under the expanded limit. After a v2 receipt is written, normal
cross-run cooldown resumes. The existing readback decision stage checks the
current source fields, verifies the hash against those fields **when the entire
body fits in the excerpt**,
and applies the same conservative hold rules used in `triage.py`. Changed
issue text that states a start prohibition, capital requirement, dependency,
unconfirmed reward, human approval gate or non-primary offer is held as such
in the current cycle — without spending another GET.

This is **negative-evidence learning only**: a source claiming it is funded
still cannot become verified or executable, and a shortened body cannot be
treated as absence of constraints. The latter receives
`RE_TRIAGE_TRUNCATED_SOURCE` unless an explicit hold is already visible in
the excerpt. The SHA-256 of the original full source content remains in the
receipt even when only the excerpt is stored. Reclassification does not
modify historical sensor observations, funding flags or policy authority.

## Readback-to-decision boundary (advisory only)

Read-only `readback_review.py` now binds the complete pre-VERIFY queue,
its three-or-fewer GitHub source-readback receipts and the readback summary
by **exact queue SHA256, original rank, URL, fingerprint, source timestamps,
snapshot flags and recorded readback time**. Missing, forged, duplicated,
inconsistent or unbound receipts cause the stage to fail closed.

The bounded observed sources are assigned distinct **review decisions**:
- `HOLD_CLOSED_SOURCE`: the issue is observed closed; do not treat as an open offer.
- `RE_TRIAGE_CHANGED_SOURCE`: the issue is still open but has changed title
  or source update time; re-evaluate its terms before proceeding.
- `HOLD_SOURCE_UNCONFIRMED`: GET failed; a network error is not proof of closure.
- `REVIEW_OPEN_UNVERIFIED`: currently open with unchanged title/update time;
  verify funding, scope and routes independently before doing any work.

The workflow preserves `readback-decisions.ndjson` and summary as SHA256-bound
artifacts alongside the original readbacks, while reporting exactly how many
sources in the full queue were **not read back** in that cycle. These are
advisory decision-quality controls, not verified funding, authorization or
a mutation of historical observations. There are still at most **three**
public GETs, zero external interactions beyond those reads, zero authorized
payments and no promotion of an experimental HOLD.

## Exact-run sensor to triage handoff

On `workflow_run`, triage must not silently analyze an unrelated moving
`main` checkout while claiming to have processed the sensor run that triggered
it. The read-only `sensor_handoff.py` resolves the **exact persisted sensor
commit** in bounded `origin/main` state-file history using the trusted GitHub
workflow-run ID. It requires agreement among state cycle ID, the last
`SENSE_COMPLETE` ledger receipt, timestamps, error list and observation counts.
If no matching, intact commit exists, the downstream job fails closed and emits
no misleading queue artifact. It never creates or changes a Git ref.

The triage job then checks out that immutable commit, runs triage and bounded
source readback, and saves its checkout SHA together with the existing SHA-256
artifact manifest. This guarantees matching **repository input provenance**,
not independent proof of external reward, approval, payment or adoption.
Manual/PR triage still evaluates its explicitly checked out revision and does
not assert that it followed a sensor cycle.

## Concurrency and crash recovery

Every active cycle holds a lease (`cycle_id`, owner, acquired/expires timestamps). A live lease causes a second scheduler to exit. Only an expired lease may be taken over. This allows redundant schedulers without duplicate work.

## Known connector-specific repair

The tested GitHub connector can branch, commit, open non-draft PRs, comment and merge in repositories with write access. It currently exposes no fork action, and its draft→ready mutation failed during testing. Therefore automated GitHub delivery creates non-draft PRs only after validation readiness and uses alternative routes or a bounded human gate for external forks.

## Enforced state and receipt contract

`validate.py` rejects `PRODUCE`, `VALIDATE`, `DELIVER`, `OBSERVE` and `SETTLE`
without a non-empty `active_opportunity.id`, a complete lease, and all eight
`policy.hard_gates` repeated as literal `true` on that opportunity. Policy flags
describe requirements; they are not proof that a particular opportunity passed.
The lease must have a named owner/cycle and timezone-aware acquisition/expiry
timestamps in increasing order. Historical validation does not establish that a
lease is currently live; the worker must check expiry before acting.

The opportunity's `delivery_route` and `settlement_route` must reference the
route registry with compatible kinds. Discovery-only, artifact-only, bridge,
and explicitly non-executable routes cannot satisfy those fields. A `dynamic`
route still requires current, opportunity-specific verification; a historic
`verified_in_test` flag alone neither grants nor denies execution authority.

Counters are non-negative integers (booleans are rejected). Cash entries need a
positive finite amount, non-empty currency/evidence, and a timezone-aware receipt
timestamp. `outcomes.ndjson` is checked as JSON records: ACCEPTED and PAID need
delivery/acceptance references, amount, currency and acceptance time. PAID also
needs `payment_evidence` and `received_at` no earlier than acceptance. Each paid
opportunity has one final PAID receipt; `counters.paid` must equal their count.
Partial transfers are not a final PAID outcome. Keep acceptance separate from
settlement, and retain earlier records when appending the final receipt.

These checks validate structure and declared gates. They do not contact sources,
authenticate receipts, prove control of a payout destination, or establish a
balance. The semantic worker must perform those independent checks before
recording verification or payment. No current opportunity, observation, award,
route permission, or realized-value bucket is changed by running the validator.

## Zero-unapproved-liability boundary

External reward opportunities may be researched without creating liabilities. No worker may commission paid third-party labor, accept fees, authorize billable API/compute usage, or infer financial consent from general autonomy permissions. Before SELECT, ACQUIRE, PRODUCE or DELIVER, the worker must assess possible costs and third-party obligations. Missing or ambiguous evidence means `PAYMENT_GATE_BLOCKED` and no external engagement. The two opportunity-level gates `no_unapproved_paid_work` and `no_unapproved_third_party_engagement` must be supported by independent evidence; `true` flags alone are not evidence of consent or no-cost execution. An externally advertised bounty payable to the contributor is not a bill payable by the beneficiary. This boundary does not cancel pre-existing agreements or prevent unrelated account subscription charges. Provider billing limits and credentials must be configured independently.

## Integrity and promotion

A successful file commit is not a successful CI run. Production promotion requires independent tests for the exact revision, plus any issue-specific held-out or live validation gates. The deterministic omega shadow driver remains HOLD until its paired trial and correction-burden evidence pass; documentation and financial-policy updates do not waive that requirement.

## Portfolio health (read only)

Run `python3 value-engine/health_report.py` for a JSON snapshot of the observation-to-settlement funnel. This command reads state without changing it, contacting providers, or treating acceptance as payment. Synthetic tests are in `test_health_report.py` and are included by the existing `test_*.py` CI discovery pattern. A report is an internal diagnostic, not independent proof of external use or cash realization.
