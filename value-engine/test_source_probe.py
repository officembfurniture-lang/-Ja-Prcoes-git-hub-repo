"""Offline source-probe tests. No external GitHub GET or paid action."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import source_probe


AT = datetime(2026, 10, 9, 17, 0, tzinfo=timezone.utc)


def queue_item(i=1, **overrides):
    row = {
        "url": f"https://github.com/example/repo/issues/{i}",
        "title": f"Bounty $95 task {i}",
        "updated_at": "2026-10-08T09:00:00Z",
        "fingerprint": f"archive-{i}",
        "status": "OBSERVED",
        "disposition": "QUEUE_VERIFY",
        "primary_source_verified": False,
        "demand_or_reward_verified": False,
        "realized_value": 0,
    }
    row.update(overrides)
    return row


def live_issue(i=1, *, state="open", **overrides):
    issue = {
        "html_url": f"https://github.com/example/repo/issues/{i}",
        "number": i,
        "state": state,
        "title": f"Bounty $95 task {i}",
        "body": "Funded claim! This text is only an assertion in the source.",
        "updated_at": "2026-10-09T16:00:00Z",
        "comments": 10,
    }
    issue.update(overrides)
    return issue


class SourceProbeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        self.queue = folder / "queue.ndjson"
        self.out = folder / "result.ndjson"
        self.summary = folder / "summary.json"

    def write(self, *rows):
        self.queue.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )

    def run_probe(self, fetcher, limit=3):
        return source_probe.probe(
            self.queue, self.out, self.summary, limit=limit,
            at=AT, fetcher=fetcher,
        )

    def receipts(self):
        return [json.loads(line) for line in self.out.read_text().splitlines()]

    def test_open_source_readback_keeps_all_authority_false(self):
        self.write(queue_item())
        summary = self.run_probe(lambda url, token: live_issue())
        receipt = self.receipts()[0]
        self.assertEqual(receipt["status"], "READBACK_OPEN")
        self.assertEqual(receipt["source_state"], "open")
        self.assertEqual(receipt["comment_count"], 10)
        self.assertEqual(receipt["source_updated_at_changed"], True)
        self.assertRegex(receipt["source_content_sha256"], r"^[a-f0-9]{64}$")
        for key, value in source_probe.NO_AUTHORITY.items():
            self.assertEqual(receipt[key], value, key)
            self.assertEqual(summary[key], value, key)
        self.assertEqual(summary["queue_sha256"],
                         hashlib.sha256(self.queue.read_bytes()).hexdigest())
        self.assertEqual(summary["attempted"], 1)

    def test_closed_issue_does_not_masquerade_as_open(self):
        self.write(queue_item())
        self.run_probe(lambda url, token: live_issue(state="closed"))
        row = self.receipts()[0]
        self.assertEqual(row["status"], "READBACK_CLOSED")
        self.assertEqual(row["source_state"], "closed")
        self.assertFalse(row["primary_source_verified"])

    def test_changed_body_or_title_has_new_canonical_hash(self):
        self.write(queue_item())
        self.run_probe(lambda url, token: live_issue())
        before = self.receipts()[0]["source_content_sha256"]
        self.run_probe(lambda url, token: live_issue(body="new content", title="new title"))
        after = self.receipts()[0]
        self.assertNotEqual(before, after["source_content_sha256"])
        self.assertTrue(after["source_title_changed"])

    def test_source_identity_and_issue_number_fail_closed(self):
        self.write(queue_item())
        for issue in (
            live_issue(number=3),
            live_issue(html_url="https://github.com/other/repo/issues/1"),
            live_issue(pull_request={"url": "https://api.github.com/foo"}),
            live_issue(state="unknown"),
        ):
            with self.subTest(issue=issue):
                self.run_probe(lambda url, token: issue)
                row = self.receipts()[0]
                self.assertEqual(row["status"], "READBACK_FAILED")
                self.assertEqual(row["error_type"], "ValueError")
                self.assertIsNone(row["source_content_sha256"])
                self.assertFalse(row["primary_source_verified"])

    def test_invalid_urls_and_forced_verification_are_never_fetched(self):
        self.write(
            queue_item(1, url="https://evil.example/issues/1"),
            queue_item(2, primary_source_verified=True),
            queue_item(3, disposition="HOLD_STALE_OBSERVATION"),
            queue_item(4),
        )
        calls = []
        def fetch(url, token):
            calls.append(url)
            return live_issue(4)
        report = self.run_probe(fetch)
        self.assertEqual(calls, ["https://github.com/example/repo/issues/4"])
        self.assertEqual(report["attempted"], 1)

    def test_no_more_than_three_gets_with_duplicate_queue_urls(self):
        self.write(*(queue_item(i) for i in [1, 1, 2, 3, 4, 5]))
        calls = []
        def fetch(url, token):
            calls.append(url)
            number = int(url.rsplit("/", 1)[1])
            return live_issue(number)
        report = self.run_probe(fetch)
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(set(calls)), 3)
        self.assertEqual(report["results"], 3)
        self.assertEqual(report["dispositions"], {"READBACK_OPEN": 3})
        self.assertEqual(len(self.receipts()), 3)

    def test_http_error_does_not_create_source_evidence(self):
        self.write(queue_item())
        def fetch(url, token):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        report = self.run_probe(fetch)
        row = self.receipts()[0]
        self.assertEqual(row["status"], "READBACK_FAILED")
        self.assertEqual(row["http_error_status"], 403)
        self.assertIsNone(row["source_content_sha256"])
        self.assertEqual(report["dispositions"], {"READBACK_FAILED": 1})

    def test_malformed_queue_fails_before_network(self):
        self.queue.write_text('{"incomplete"\n', encoding="utf-8")
        with self.assertRaises(ValueError):
            self.run_probe(lambda url, token: self.fail("must not fetch"))

    def test_limit_cannot_exceed_three(self):
        self.write(queue_item())
        with self.assertRaises(ValueError):
            self.run_probe(lambda url, token: self.fail("must not fetch"), limit=10)

    def test_repeat_with_same_source_and_clock_is_reproducible(self):
        self.write(queue_item())
        def fetch(url, token):
            return live_issue()
        self.run_probe(fetch)
        first = (self.out.read_bytes(), self.summary.read_bytes())
        self.run_probe(fetch)
        self.assertEqual(first, (self.out.read_bytes(), self.summary.read_bytes()))


if __name__ == "__main__":
    unittest.main()
