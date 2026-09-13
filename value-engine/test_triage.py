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
