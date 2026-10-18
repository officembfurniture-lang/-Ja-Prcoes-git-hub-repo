"""Offline regressions for cross-run source readback cooldown feedback."""
import json
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

import readback_cooldown
import source_probe

AT = datetime(2026, 10, 11, 11, 0, tzinfo=timezone.utc)


def candidate(i):
    return {
        "url": f"https://github.com/example/repo/issues/{i}",
        "title": f"Reward $100 issue {i}",
        "updated_at": "2026-10-11T10:00:00Z",
        "fingerprint": f"revision-{i}",
        "status": "OBSERVED",
        "disposition": "QUEUE_VERIFY",
        "primary_source_verified": False,
        "demand_or_reward_verified": False,
        "realized_value": 0,
    }


def live_issue(i, state="open"):
    return {
        "html_url": f"https://github.com/example/repo/issues/{i}",
        "number": i, "state": state,
        "title": f"Reward $100 issue {i}",
        "body": "No confirmed payment; synthetic fixture.",
        "updated_at": "2026-10-11T10:00:00Z",
    }


class CrossRunFeedbackTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.previous = root / "old"
        self.previous.mkdir()
        self.queue = root / "new-queue.ndjson"
        self.output = root / "new-readbacks.ndjson"
        self.summary = root / "new-summary.json"
        self.old_queue = self.previous / "value-engine-triage-queue.ndjson"
        self.old_readbacks = self.previous / "value-engine-source-readback.ndjson"
        self.old_summary = self.previous / "value-engine-source-readback-summary.json"
        self.rows = [candidate(i) for i in range(1, 8)]
        self.write_queue(self.rows, self.old_queue)
        self.write_queue(self.rows, self.queue)

    @staticmethod
    def write_queue(rows, path):
        path.write_text("".join(json.dumps(row) + "\n" for row in rows),
                        encoding="utf-8")

    def prior_probe(self, fetcher=None):
        if fetcher is None:
            fetcher = lambda url, token: live_issue(int(url.rsplit("/", 1)[1]))
        return source_probe.probe(
            self.old_queue, self.old_readbacks, self.old_summary, at=AT,
            rotation=0, fetcher=fetcher,
        )

    def fresh_probe(self, at=None, prior=True, **kwargs):
        calls = []
        def fetch(url, token):
            n = int(url.rsplit("/", 1)[1])
            calls.append(n)
            return live_issue(n)
        result = source_probe.probe(
            self.queue, self.output, self.summary,
            at=at or AT + timedelta(hours=1),
            prior_bundle=self.previous if prior else None,
            fetcher=fetch, rotation=0, **kwargs,
        )
        return result, calls

    def test_successful_prior_gets_reallocate_budget_without_extra_get(self):
        self.prior_probe()
        result, calls = self.fresh_probe()
        self.assertEqual(calls, [4, 5, 6])
        self.assertEqual(result["selected_queue_ranks"], [4, 5, 6])
        self.assertEqual(result["attempted"], 3)
        self.assertEqual(result["prior_feedback_status"], "SUPPRESSION_APPLIED")
        self.assertEqual(result["eligible_unique_urls"], 7)
        self.assertEqual(result["eligible_after_recent_cooldown"], 4)
        self.assertEqual(
            result["recent_readbacks_skipped"],
            [{"queue_rank": i, "prior_status": "READBACK_OPEN"} for i in (1, 2, 3)],
        )
        self.assertFalse(result["authorization_to_execute"])
        self.assertFalse(result["primary_source_verified"])

    def test_prior_closed_and_404_are_temporary_and_distinct(self):
        def fetch(url, token):
            n = int(url.rsplit("/", 1)[1])
            if n == 1:
                return live_issue(n, state="closed")
            if n == 2:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            return live_issue(n)
        self.prior_probe(fetch)
        at = AT + timedelta(hours=3)
        current = list(enumerate(self.rows, 1))
        skipped = readback_cooldown.recent_readback_suppressions(
            self.previous, at, current)
        self.assertEqual(skipped, {
            "https://github.com/example/repo/issues/1": "READBACK_CLOSED",
            "https://github.com/example/repo/issues/2": "READBACK_FAILED"})
        result, calls = self.fresh_probe(at=at)
        self.assertEqual(calls, [3, 4, 5])
        self.assertEqual(result["recent_readbacks_skipped"], [
            {"queue_rank": 1, "prior_status": "READBACK_CLOSED"},
            {"queue_rank": 2, "prior_status": "READBACK_FAILED"},
        ])
        # Closed records and a stable 404 are temporary readback hints, not
        # permanent tombstones. Both become eligible after their TTLs expire.
        after_ttl, after_calls = self.fresh_probe(at=AT + timedelta(days=7))
        self.assertEqual(after_calls, [1, 2, 3])
        self.assertEqual(after_ttl["recent_readbacks_skipped"], [])
        self.assertEqual(after_ttl["prior_feedback_status"], "VALID_NO_SUPPRESSION")

    def test_changed_source_fingerprint_is_never_suppressed(self):
        self.prior_probe()
        modified = [dict(row) for row in self.rows]
        modified[0]["fingerprint"] = "newer-source-revision"
        self.write_queue(modified, self.queue)
        report, calls = self.fresh_probe()
        self.assertEqual(calls, [1, 4, 5])
        self.assertEqual(report["selected_queue_ranks"], [1, 4, 5])
        self.assertEqual(len(report["recent_readbacks_skipped"]), 2)

    def test_404_cooldown_does_not_freeze_a_new_source_revision(self):
        def fetch(url, token):
            n = int(url.rsplit("/", 1)[1])
            if n == 2:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            return live_issue(n)

        self.prior_probe(fetch)
        changed = [dict(row) for row in self.rows]
        changed[1]["fingerprint"] = "newly-discovered-revision"
        self.write_queue(changed, self.queue)

        result, calls = self.fresh_probe(at=AT + timedelta(hours=3))
        self.assertIn(2, calls)
        self.assertEqual(result["recent_readbacks_skipped"], [])
        self.assertEqual(result["prior_feedback_status"], "VALID_NO_SUPPRESSION")

    def test_legacy_v1_truncated_receipts_cannot_suppress_new_full_body_reads(self):
        self.prior_probe()
        summary = json.loads(self.old_summary.read_text())
        summary["schema"] = "value-engine.source-readback/v1"
        self.old_summary.write_text(json.dumps(summary), encoding="utf-8")

        result, calls = self.fresh_probe(at=AT + timedelta(minutes=1))
        self.assertEqual(calls, [1, 2, 3])
        self.assertEqual(result["prior_feedback_status"],
                         "INVALID_FALLBACK_TO_FRESH_GET")
        self.assertEqual(result["recent_readbacks_skipped"], [])

    def test_malformed_prior_artifacts_fall_back_to_fresh_get(self):
        self.prior_probe()
        original = self.old_readbacks.read_bytes()
        old = [json.loads(s) for s in original.splitlines()]
        attempts = [
            ("altered rank", [dict(row, queue_rank=99) for row in old]),
            ("claimed authority", [dict(old[0], authorization_to_execute=True)] + old[1:]),
        ]
        for label, values in attempts:
            with self.subTest(label=label):
                self.old_readbacks.write_text(
                    "".join(json.dumps(x) + "\n" for x in values))
                report, calls = self.fresh_probe()
                self.assertEqual(calls, [1, 2, 3])
                self.assertEqual(report["prior_feedback_status"],
                                 "INVALID_FALLBACK_TO_FRESH_GET")
                self.assertEqual(report["recent_readbacks_skipped"], [])
        self.old_readbacks.write_bytes(original)
        # Missing artifact is normal on the very first successful run.
        self.old_readbacks.unlink()
        report, calls = self.fresh_probe()
        self.assertEqual(calls, [1, 2, 3])
        self.assertEqual(report["prior_feedback_status"],
                         "INVALID_FALLBACK_TO_FRESH_GET")

    def test_future_feedback_cannot_suppress_and_is_not_a_live_state_claim(self):
        self.prior_probe()
        summary, calls = self.fresh_probe(at=AT - timedelta(minutes=1))
        self.assertEqual(calls, [1, 2, 3])
        self.assertEqual(summary["prior_feedback_status"],
                         "INVALID_FALLBACK_TO_FRESH_GET")
        self.assertEqual(summary["dispositions"], {"READBACK_OPEN": 3})
        self.assertNotIn("READBACK_CLOSED", summary["dispositions"])

    def test_nonconforming_old_failed_receipt_can_never_skip_current_url(self):
        def fetch(url, token):
            raise urllib.error.HTTPError(url, 500, "Server Error", {}, None)
        self.prior_probe(fetch)
        report, calls = self.fresh_probe()
        self.assertEqual(calls, [1, 2, 3])
        self.assertEqual(report["recent_readbacks_skipped"], [])
        self.assertEqual(report["prior_feedback_status"], "VALID_NO_SUPPRESSION")
        self.assertFalse(report["authorization_to_execute"])


if __name__ == "__main__":
    unittest.main()
