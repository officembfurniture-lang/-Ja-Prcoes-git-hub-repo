# Preserve an explicit prohibition to begin work

A current source review on 23 September 2026 found that [KushBitx #1](https://github.com/kushBitxHQ/kushbitx-sdk/issues/1) was still open for payout reconciliation after its sole award had been assigned. The source expressly prohibited further work. Running the unchanged selector against that fresh body still returned `QUEUE_VERIFY` with score 16 and no risks: the existing start-prohibition vocabulary recognized “do not start” but omitted “do not begin”.

The source was updated after the latest recorded sensor snapshot. This does not prove the earlier snapshot was incorrect; the defect was reproduced on the newly fetched text. No production observation or accounting record is rewritten.

The fix adds the missing phrase to the existing highest-priority `HOLD_START_PROHIBITED` branch. It introduces no controller, permission, execution path, payout claim, or general prohibition on previously awarded or multi-award offers. Triage remains a conservative text pre-filter, not verification of source authority or meaning.

Four additional tests cover the observed prohibition (including uppercase wording), an allowed free acceptance path, an open multi-award offer, and queue removal when a newer source revision prohibits starting. Before the fix the new prohibition and pipeline checks failed; after the fix all 52 VALUE_ENGINE tests pass. `compileall`, state validation and whitespace checks pass.

The same-input comparison across 3,243 current candidates (with that one refreshed source) changes two dispositions:

| Source | Before | After |
|---|---|---|
| KushBitx SDK #1 | QUEUE_VERIFY | HOLD_START_PROHIBITED |
| Mycelix #805 | DROP_LOW_SIGNAL | HOLD_START_PROHIBITED |

The latter captured source prohibits starting dependent implementation before its predecessor qualifies; the repair preserves that reason rather than reducing it to a low score. This comparison is defect-driven regression evidence, not a held-out performance estimate. Ω Issue #2 and its human-burden measurement gate are unaffected.

Local receipt and source hashes are in `triage-start-prohibition-evidence-2026-09-23.json`. Remote CI is reported separately only after completion. A pre-filter still cannot replace a fresh source read before work is selected.
