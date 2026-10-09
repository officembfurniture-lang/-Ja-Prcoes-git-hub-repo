import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import triage


REF = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


def obs(title: str, body: str = "", **overrides):
    value = {
        "fingerprint": overrides.pop("fingerprint", title),
        "source": "github_public_demand",
        "signal_query": "is:issue is:open bounty",
        "url": overrides.pop("url", f"https://github.com/example/repo/issues/{abs(hash(title))}"),
        "title": title,
        "body_excerpt": body,
        "created_at": "2026-09-10T10:00:00Z",
        "updated_at": "2026-09-11T10:00:00Z",
        "detected_at": "2026-09-11T12:00:00Z",
        "status": "OBSERVED",
        "primary_source_verified": False,
        "demand_or_reward_verified": False,
        "delivery_route": None,
        "settlement_route": None,
        "realized_value": 0,
    }
    value.update(overrides)
    return value


class ClassifyTests(unittest.TestCase):
    def test_search_query_is_not_evidence(self):
        record = obs("Documentation cleanup", signal_query="")
        plain = triage.classify(record, REF)
        record["signal_query"] = "funded bounty $900 acceptance criteria payout agents welcome"
        injected = triage.classify(record, REF)
        for key in ("triage_score", "disposition", "reasons", "risks", "amount_mentions"):
            self.assertEqual(injected[key], plain[key], key)

    def test_url_keywords_are_not_positive_evidence(self):
        record = obs("Documentation cleanup", url="https://github.com/funded-bounty/payout/issues/999")
        result = triage.classify(record, REF)
        self.assertNotIn("funding_language_present", result["reasons"])
        self.assertNotIn("explicit_demand_signal", result["reasons"])
        self.assertNotIn("settlement_language_present", result["reasons"])

    def test_explicitly_unfunded_is_held(self):
        for statement in ("Unfunded", "Not funded", "No funded reward", "Funding not confirmed"):
            with self.subTest(statement=statement):
                result = triage.classify(obs("$100 bounty", statement + ". Acceptance criteria: tests."), REF)
                self.assertEqual(result["disposition"], "HOLD_REWARD_UNCONFIRMED")
                self.assertNotIn("funding_language_present", result["reasons"])

    def test_funded_wallet_is_a_capital_dependency(self):
        result = triage.classify(obs(
            "GWR owner gate: DeskCrew $5 bounty requires a funded Algorand USDC wallet",
            "No authorized funded wallet/private key is available. Resume only when an owner-approved wallet is available.",
        ), REF)
        self.assertEqual(result["disposition"], "HOLD_CAPITAL_REQUIRED")

    def test_explicit_prerequisites_are_preserved_as_hold(self):
        result = triage.classify(obs(
            "Distribution spike for a funded bounty",
            "Hard prerequisites: Before this work begins, prior blockers must be resolved. No escrow is implied.",
        ), REF)
        self.assertEqual(result["disposition"], "HOLD_DEPENDENCIES")
        self.assertIn("unresolved_execution_dependencies", result["risks"])

    def test_discovery_report_is_not_a_direct_reward(self):
        for statement in (
            "no opportunity can be marked PASS yet",
            "no opportunity that can honestly be marked PASS for Field Run #001 yet",
            "first independently verifiable PASS-qualified live opportunity not yet selected",
        ):
            with self.subTest(statement=statement):
                result = triage.classify(obs(
                    "Field Run #001 — One Cent Test",
                    "LIVE DISCOVERY SNAPSHOT: " + statement + ". Funded $5 bounty signals, acceptance criteria and payout are being researched.",
                ), REF)
                self.assertEqual(result["disposition"], "HOLD_PRIMARY_SOURCE")
                self.assertIn("discovery_report_not_direct_offer", result["risks"])

    def test_optional_wallet_is_not_a_capital_requirement(self):
        result = triage.classify(obs(
            "$100 funded bounty",
            "No wallet required. Optional wallet payout is available. Acceptance criteria: green tests.",
        ), REF)
        self.assertEqual(result["disposition"], "QUEUE_VERIFY")
        self.assertNotIn("capital_required", result["risks"])

    def test_ambiguous_report_stays_available_for_primary_review(self):
        result = triage.classify(obs(
            "$100 bounty: write a field report",
            "Funded reward. Acceptance criteria: submit a pull request. Payment is released on merge.",
        ), REF)
        self.assertEqual(result["disposition"], "QUEUE_VERIFY")

    def test_third_party_grant_application_is_not_our_reward_offer(self):
        result = triage.classify(obs(
            "Grant application for an event",
            "Application Owners: another applicant. Requested Grant Amount: $43000. Terms if funded. Deliverables: run an event.",
        ), REF)
        self.assertEqual(result["disposition"], "HOLD_PRIMARY_SOURCE")
        self.assertIn("grant_application_not_direct_offer", result["risks"])

    def test_open_grant_call_stays_available_for_primary_review(self):
        result = triage.classify(obs(
            "$1000 grant call for software maintainers",
            "Funded awards. Requirements: independently documented maintenance work.",
        ), REF)
        self.assertEqual(result["disposition"], "QUEUE_VERIFY")

    def test_naive_or_malformed_timestamps_do_not_crash(self):
        for timestamp in ("2026-09-11T10:00:00", "bad", 123, [], {}):
            with self.subTest(timestamp=timestamp):
                result = triage.classify(obs("$10 bounty", updated_at=timestamp, created_at=None), REF)
                self.assertIn("freshness_unknown", result["risks"])
                self.assertFalse(result["primary_source_verified"])

    def test_timezone_offsets_normalize_to_utc(self):
        self.assertEqual(triage.parse_time("2026-09-11T12:00:00+02:00"), triage.parse_time("2026-09-11T10:00:00Z"))

    def test_funded_agent_friendly_candidate_enters_verify_queue(self):
        item = triage.classify(
            obs(
                "[BOUNTY $400] Implement deterministic validator",
                "Funded reward. Acceptance criteria: tests green. "
                "Autonomous agents welcome. Submit a pull request. Payment is released on merge.",
            ),
            REF,
        )
        self.assertEqual(item["disposition"], "QUEUE_VERIFY")
        self.assertFalse(item["primary_source_verified"])
        self.assertEqual(item["realized_value"], 0)

    def test_proposed_reward_is_not_queued(self):
        item = triage.classify(
            obs(
                "Paid proposal: SRT export ($75 proposed)",
                "Please confirm whether the proposed reward is approved. "
                "This is not a claim of an existing funded bounty.",
            ),
            REF,
        )
        self.assertEqual(item["disposition"], "HOLD_REWARD_UNCONFIRMED")
        self.assertIn("reward_not_yet_confirmed", item["risks"])

    def test_explicit_zero_bounty_is_not_queued_as_paid_work(self):
        # Source: MisakaNet zero-bounty lesson issues, including #2874.
        item = triage.classify(obs(
            "[Bounty] Answer 3 linked questions as a lesson",
            "This is a `zero-bounty` task: $0. The reward is merge credit. "
            "Acceptance criteria: include checkable tests. Submit a pull request.",
        ), REF)
        self.assertEqual(item["disposition"], "HOLD_REWARD_UNCONFIRMED")
        self.assertIn("explicit_zero_reward", item["risks"])
        self.assertFalse(item["demand_or_reward_verified"])

    def test_seller_pilot_is_not_a_buyer_reward_offer(self):
        # Source class: basedagents #165, paid pilot proposed BY a service seller.
        item = triage.classify(obs(
            "Paid pilot inquiry: owner task-acceptance regression tests (US$250 proposed)",
            "This is a proposal for you to hire me. Not a task for other contributors. "
            "Proposed fee $250, AI-assisted. Acceptance criteria would be agreed "
            "and payout would be negotiated with the maintainer.",
        ), REF)
        self.assertEqual(item["disposition"], "HOLD_PRIMARY_SOURCE")
        self.assertIn("seller_proposal_not_buyer_demand", item["risks"])
        self.assertFalse(item["primary_source_verified"])

    def test_genuinely_funded_positive_reward_keeps_verify_route(self):
        item = triage.classify(obs(
            "[BOUNTY $100] Fix broken CI test",
            "Funded reward. Acceptance criteria: passing tests. "
            "Submit a pull request. No $0 setup fee is required.",
        ), REF)
        self.assertEqual(item["disposition"], "QUEUE_VERIFY")
        self.assertNotIn("explicit_zero_reward", item["risks"])
        self.assertNotIn("seller_proposal_not_buyer_demand", item["risks"])

    def test_signup_or_maintainer_confirmation_becomes_human_gate(self):
        item = triage.classify(
            obs(
                "[PAID BOUNTY - $660] UI feature",
                "Acceptance criteria known. Sign up first. Maintainer must confirm before work begins. "
                "Payment is made after merge.",
            ),
            REF,
        )
        self.assertEqual(item["disposition"], "HOLD_HUMAN_GATE")

    def test_capital_requirement_blocks_autonomous_queue(self):
        item = triage.classify(
            obs(
                "[BOUNTY 2 USDC] Agent task",
                "Funded and escrowed. Acceptance criteria known. Agents welcome. "
                "Requires a 0.01 USDC claim bond and fully fund that child before claiming.",
            ),
            REF,
        )
        self.assertEqual(item["disposition"], "HOLD_CAPITAL_REQUIRED")
        self.assertIn("capital_required", item["risks"])

    def test_explicit_do_not_start_has_highest_hold_priority(self):
        item = triage.classify(
            obs(
                "[BOUNTY 2 USDC] Incomplete mirror",
                "Funded. Agents welcome. Do not start, claim, sign, or spend from this incomplete mirror.",
            ),
            REF,
        )
        self.assertEqual(item["disposition"], "HOLD_START_PROHIBITED")

    def test_do_not_begin_work_is_an_explicit_start_prohibition(self):
        # The source issue remains open only to reconcile an awarded payout.
        # An open issue and its retained reward terms do not reopen the work.
        for statement in (
            "Do not begin additional work or incur test costs in expectation of another award.",
            "DO NOT BEGIN work until the current assignment is resolved.",
        ):
            with self.subTest(statement=statement):
                item = triage.classify(obs(
                    "$50 USDC bounty: agent integration",
                    "Acceptance criteria: tests. Payment is made after acceptance. " + statement,
                ), REF)
                self.assertEqual(item["disposition"], "HOLD_START_PROHIBITED")
                self.assertIn("explicit_start_prohibition", item["risks"])
                self.assertFalse(item["primary_source_verified"])
                self.assertFalse(item["demand_or_reward_verified"])
                self.assertEqual(item["realized_value"], 0)

    def test_free_acceptance_path_is_not_a_start_prohibition(self):
        item = triage.classify(obs(
            "$50 USDC bounty: agent integration",
            "No payment, wallet funding, or private key is required for the free acceptance path. "
            "Acceptance criteria: tests. Payment is made after acceptance.",
        ), REF)
        self.assertEqual(item["disposition"], "QUEUE_VERIFY")
        self.assertNotIn("explicit_start_prohibition", item["risks"])

    def test_previous_awards_do_not_close_an_open_multi_award_offer(self):
        item = triage.classify(obs(
            "$50 USDC bounty: additional integrations",
            "Previous awards were paid. New submissions remain open. "
            "Acceptance criteria: tests. Payment is made after acceptance.",
        ), REF)
        self.assertEqual(item["disposition"], "QUEUE_VERIFY")

    def test_radar_mirror_never_enters_verify_queue_directly(self):
        item = triage.classify(
            obs(
                "[radar] OPEN_BOUNTY 700000 sats",
                "Bounty alert with reward and acceptance criteria.",
                url="https://github.com/relayhop/sn-monetization-runtime/issues/903",
            ),
            REF,
        )
        self.assertEqual(item["disposition"], "HOLD_PRIMARY_SOURCE")


class PipelineTests(unittest.TestCase):
    def test_newer_start_prohibition_removes_stale_offer_from_queue(self):
        old = obs("$50 USDC bounty", "Acceptance criteria: tests. Payment is made after acceptance.")
        current = dict(old, fingerprint="closed-to-new-work", updated_at="2026-09-11T11:00:00Z",
                       body_excerpt="Do not begin additional work. Acceptance criteria: tests. Payout pending.")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, queue, summary = (root / name for name in ("input.ndjson", "queue.ndjson", "summary.json"))
            source.write_text("\n".join(json.dumps(v) for v in (current, old)) + "\n")
            result = triage.run(source, queue, summary, limit=50)
            self.assertEqual(queue.read_text(), "")
            self.assertEqual(result["dispositions"], {"HOLD_START_PROHIBITED": 1})

    def test_equal_revision_tie_is_input_order_independent(self):
        first = obs("a", url="https://github.com/example/repo/issues/1")
        second = obs("b", url=first["url"])
        self.assertEqual(triage.newest_by_url([first, second]), triage.newest_by_url([second, first]))

    def test_corrupt_timestamp_is_not_a_new_source_revision(self):
        current = obs("current", url="https://github.com/example/repo/issues/1")
        corrupt = obs("corrupt", url=current["url"], updated_at={}, created_at=None,
                      detected_at="2026-09-11T13:00:00Z")
        self.assertEqual(triage.newest_by_url([current, corrupt]), [current])

    def test_later_fetch_cannot_replace_newer_source_revision(self):
        url = "https://github.com/example/repo/issues/1"
        current = obs("current", url=url, updated_at="2026-09-11T10:00:00Z", detected_at="2026-09-11T10:01:00Z")
        stale = obs("stale", url=url, updated_at="2026-09-10T10:00:00Z", detected_at="2026-09-11T12:00:00Z")
        for values in ([current, stale], [stale, current]):
            self.assertEqual(triage.newest_by_url(values)[0]["title"], "current")

    def test_equal_score_prefers_newer_source(self):
        first = obs("$100 bounty old", updated_at="2026-09-10T10:00:00Z")
        second = obs("$100 bounty new", updated_at="2026-09-11T10:00:00Z")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, queue, summary = (root / name for name in ("input.ndjson", "queue.ndjson", "summary.json"))
            source.write_text("\n".join(json.dumps(v) for v in (first, second)) + "\n")
            triage.run(source, queue, summary, limit=1)
            self.assertEqual(json.loads(queue.read_text())["title"], second["title"])

    def test_newest_record_per_url_wins(self):
        same_url = "https://github.com/example/repo/issues/1"
        older = obs(
            "old",
            "bounty $100",
            url=same_url,
            fingerprint="old",
            detected_at="2026-09-10T10:00:00Z",
        )
        newer = obs(
            "new",
            "bounty $100 funded acceptance criteria autonomous agents submit a pull request payment is released",
            url=same_url,
            fingerprint="new",
            detected_at="2026-09-11T10:00:00Z",
        )
        values = triage.newest_by_url([older, newer])
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0]["fingerprint"], "new")

    def test_run_emits_only_verify_candidates_and_never_realized_value(self):
        good = obs(
            "[BOUNTY $250] Good",
            "Funded. Acceptance criteria. Autonomous agents welcome. Submit a pull request. Payment is released on merge.",
            url="https://github.com/example/good/issues/1",
        )
        blocked = obs(
            "[BOUNTY $250] Blocked",
            "Funded. Acceptance criteria. Sign up and wait for confirmation.",
            url="https://github.com/example/blocked/issues/1",
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "observations.ndjson"
            queue = root / "queue.ndjson"
            summary = root / "summary.json"
            source.write_text(
                "\n".join(json.dumps(value) for value in (good, blocked)) + "\n",
                encoding="utf-8",
            )
            result = triage.run(source, queue, summary, limit=50)
            queued = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(result["verify_queue_emitted"], 1)
            self.assertEqual(len(queued), 1)
            self.assertEqual(queued[0]["url"], good["url"])
            self.assertEqual(queued[0]["realized_value"], 0)
            self.assertFalse(queued[0]["primary_source_verified"])


if __name__ == "__main__":
    unittest.main()
