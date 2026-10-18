"""Offline source-readback decision regressions; no network or execution."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import readback_review
import source_probe

AT = datetime(2026, 10, 11, 9, 39, 0, tzinfo=timezone.utc)


def queue_row(i):
    return {
        "url": f"https://github.com/example/repo/issues/{i}",
        "title": f"Bounty $100 task {i}",
        "updated_at": "2026-10-11T09:00:00Z",
        "fingerprint": f"revision-{i}",
        "status": "OBSERVED",
        "disposition": "QUEUE_VERIFY",
        "primary_source_verified": False,
        "demand_or_reward_verified": False,
        "realized_value": 0,
    }


def live_issue(i, state="open", updated="2026-10-11T09:00:00Z", **kwargs):
    return dict(
        html_url=f"https://github.com/example/repo/issues/{i}",
        number=i, state=state, title=f"Bounty $100 task {i}",
        body="Source assertion: fully funded; not independently verified.",
        updated_at=updated, comments=2, **kwargs,
    )


class ReadbackReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.queue = root / "queue.ndjson"
        self.receipts = root / "readbacks.ndjson"
        self.probe_summary = root / "probe-summary.json"
        self.output = root / "review-decisions.ndjson"
        self.summary = root / "review-summary.json"

    def prepare(self, fetcher, *, count=4):
        self.queue.write_text(
            "".join(json.dumps(queue_row(i)) + "\n" for i in range(1, count + 1)),
            encoding="utf-8",
        )
        source_probe.probe(
            self.queue, self.receipts, self.probe_summary, limit=3,
            rotation=0, at=AT, fetcher=fetcher,
        )

    def review(self):
        result = readback_review.run(
            self.queue, self.receipts, self.probe_summary, self.output, self.summary)
        rows = [json.loads(line) for line in self.output.read_text().splitlines()]
        return result, rows

    def test_closed_changed_failed_yield_three_distinct_review_decisions(self):
        def fetcher(url, token):
            n = int(url.rsplit("/", 1)[1])
            if n == 1:
                return live_issue(n, state="closed")
            if n == 2:
                return live_issue(n, updated="2026-10-11T09:30:00Z")
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        self.prepare(fetcher)
        summary, rows = self.review()
        self.assertEqual(
            [x["review_decision"] for x in rows],
            ["HOLD_CLOSED_SOURCE", "RE_TRIAGE_CHANGED_SOURCE",
             "HOLD_SOURCE_UNCONFIRMED"],
        )
        self.assertEqual(summary["queue_count"], 4)
        self.assertEqual(summary["readback_count"], 3)
        self.assertEqual(summary["not_read_back_count"], 1)
        self.assertEqual(summary["selected_queue_ranks"], [1, 2, 3])
        self.assertEqual(rows[0]["readback_status"], "READBACK_CLOSED")
        self.assertEqual(rows[2]["readback_status"], "READBACK_FAILED")
        self.assertIsNone(rows[2]["source_content_sha256"])
        self.assertFalse(summary["authorization_to_execute"])
        self.assertFalse(summary["demand_or_reward_verified"])
        self.assertEqual(summary["realized_value"], 0)
        for row in rows:
            self.assertFalse(row["primary_source_verified"])
            self.assertFalse(row["demand_or_reward_verified"])
            self.assertFalse(row["authorization_to_execute"])
            self.assertEqual(row["realized_value"], 0)

    def test_open_unchanged_source_remains_unverified(self):
        self.prepare(lambda url, token: live_issue(int(url.rsplit("/", 1)[1])))
        summary, rows = self.review()
        self.assertEqual(summary["review_decisions"],
                         {"REVIEW_OPEN_UNVERIFIED": 3})
        self.assertTrue(all(x["authority"] == "ADVISORY_ONLY" for x in rows))

    def test_source_stop_capital_and_unfunded_holds_reused_from_same_get(self):
        snippets = {
            1: "Do not start this task. Acceptance criteria: tests.",
            2: "Claim bond required. Stake required to begin.",
            3: "Not funded. No reward confirmed.",
        }
        calls = []
        def fetcher(url, token):
            n = int(url.rsplit("/", 1)[1])
            calls.append(n)
            return dict(live_issue(n), body=snippets[n])
        self.prepare(fetcher)
        summary, rows = self.review()
        self.assertEqual(calls, [1, 2, 3])
        self.assertEqual(
            [r["review_decision"] for r in rows],
            ["HOLD_START_PROHIBITED", "HOLD_CAPITAL_REQUIRED",
             "HOLD_REWARD_UNCONFIRMED"])
        self.assertEqual(
            [r["current_source_policy"] for r in rows],
            ["HOLD_START_PROHIBITED", "HOLD_CAPITAL_REQUIRED",
             "HOLD_REWARD_UNCONFIRMED"])
        self.assertFalse(summary["authorization_to_execute"])

    def test_truncated_source_tail_requires_explicit_extra_review(self):
        body = ("Ordinary issue details. " * 1100) + "Do not start."
        self.assertGreater(len(body), readback_review.MAX_SOURCE_BODY_CHARS)
        self.prepare(lambda url, token: dict(
            live_issue(int(url.rsplit("/", 1)[1])), body=body))
        summary, rows = self.review()
        self.assertEqual(summary["review_decisions"],
                         {"RE_TRIAGE_TRUNCATED_SOURCE": 3})
        self.assertTrue(all(row["source_body_truncated"] for row in rows))
        self.assertFalse(summary["primary_source_verified"])

    def test_full_body_with_tail_prohibition_is_held_not_truncated(self):
        body = ("Ordinary issue details. " * 430) + "\nDO NOT START THIS TASK"
        self.assertGreater(len(body), 18_000)
        self.assertLessEqual(len(body), readback_review.MAX_SOURCE_BODY_CHARS)
        self.prepare(lambda url, token: dict(
            live_issue(int(url.rsplit("/", 1)[1])), body=body))
        summary, rows = self.review()
        self.assertEqual(summary["review_decisions"], {"HOLD_START_PROHIBITED": 3})
        self.assertTrue(all(not row["source_body_truncated"] for row in rows))
        self.assertTrue(all("DO NOT START THIS TASK" in
                            row["source_body_excerpt"] for row in rows))
        self.assertFalse(summary["authorization_to_execute"])

    def test_source_body_or_drift_flag_tampering_is_rejected(self):
        self.prepare(lambda url, token: live_issue(int(url.rsplit("/", 1)[1])))
        original = [json.loads(x) for x in self.receipts.read_text().splitlines()]
        for field, value in (
            ("source_body_excerpt", "changed text without corresponding digest"),
            ("source_title_changed", True),
            ("source_updated_at_changed", True),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(original)
                changed[0][field] = value
                self.receipts.write_text(
                    "".join(json.dumps(x) + "\n" for x in changed), encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.review()

    def test_same_gets_support_current_policy_without_more_network(self):
        calls = []
        def fetcher(url, token):
            calls.append(url)
            return dict(live_issue(int(url.rsplit("/", 1)[1])),
                        body="No wallet required. Acceptance criteria: tests.")
        self.prepare(fetcher)
        self.assertEqual(len(calls), 3)
        summary, rows = self.review()
        self.assertEqual(len(calls), 3)
        self.assertEqual(summary["review_decisions"],
                         {"REVIEW_OPEN_UNVERIFIED": 3})
        self.assertTrue(all(row["authority"] == "ADVISORY_ONLY" for row in rows))

    def test_same_inputs_have_byte_identical_decisions(self):
        self.prepare(lambda url, token: live_issue(int(url.rsplit("/", 1)[1])))
        first = self.review()
        first_bytes = (self.output.read_bytes(), self.summary.read_bytes())
        self.assertEqual(first, self.review())
        self.assertEqual(first_bytes,
                         (self.output.read_bytes(), self.summary.read_bytes()))

    def test_cross_run_queue_and_source_identity_tampering_fail_closed(self):
        self.prepare(lambda url, token: live_issue(int(url.rsplit("/", 1)[1])))
        original_queue = self.queue.read_bytes()
        original_receipts = self.receipts.read_bytes()
        original_probe = self.probe_summary.read_bytes()
        queue_lines = original_queue.splitlines()
        queue_lines[0] = queue_lines[0].replace(b"revision-1", b"revision-hijack")
        with self.subTest("queue contents modified"):
            self.queue.write_bytes(b"\n".join(queue_lines) + b"\n")
            with self.assertRaisesRegex(ValueError, "bind this queue"):
                self.review()
            self.queue.write_bytes(original_queue)
        values = [json.loads(x) for x in original_receipts.splitlines()]
        for field, value in (("queue_rank", 999), ("queue_source_url", "https://github.com/evil/repo/issues/1"),
                             ("queue_fingerprint", "forged"), ("readback_at", "2026-01-01T00:00:00Z"),
                             ("status", "READBACK_CLOSED")):
            with self.subTest(field=field):
                altered = copy.deepcopy(values)
                altered[0][field] = value
                self.receipts.write_text(
                    "".join(json.dumps(x) + "\n" for x in altered), encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.review()
        self.receipts.write_bytes(original_receipts)
        with self.subTest("invalid duplicated ranks"):
            altered = copy.deepcopy(values)
            altered[1]["queue_rank"] = altered[0]["queue_rank"]
            self.receipts.write_text(
                "".join(json.dumps(x) + "\n" for x in altered), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.review()
        self.receipts.write_bytes(original_receipts)
        self.probe_summary.write_bytes(original_probe)

    def test_false_authority_and_boolean_realized_value_are_rejected(self):
        self.prepare(lambda url, token: live_issue(int(url.rsplit("/", 1)[1])))
        a = [json.loads(x) for x in self.receipts.read_text().splitlines()]
        for field, value in (("primary_source_verified", True),
                             ("authorization_to_execute", 1),
                             ("realized_value", True),
                             ("realized_value", 1)):
            with self.subTest(field=field, value=value):
                altered = copy.deepcopy(a)
                altered[0][field] = value
                self.receipts.write_text(
                    "".join(json.dumps(x) + "\n" for x in altered), encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.review()

    def test_source_failure_does_not_become_source_closed(self):
        self.prepare(
            lambda url, token: (_ for _ in ()).throw(
                urllib.error.HTTPError(url, 403, "Forbidden", {}, None)),
            count=3,
        )
        summary, rows = self.review()
        self.assertEqual(summary["review_decisions"],
                         {"HOLD_SOURCE_UNCONFIRMED": 3})
        self.assertEqual({r["readback_status"] for r in rows}, {"READBACK_FAILED"})
        self.assertFalse(self.output.read_text().find("HOLD_CLOSED_SOURCE") >= 0)


if __name__ == "__main__":
    unittest.main()
