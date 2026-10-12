"""Offline, deterministic regressions for source-revision snapshot refresh.

All GitHub responses and clock readings are synthetic. No network or paid work.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import urllib.error
import urllib.request
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import cycle


START = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def source_item() -> dict:
    return {
        "id": 320,
        "number": 320,
        "html_url": "https://github.com/example/repo/issues/320",
        "updated_at": "2026-10-01T11:00:00Z",
        "created_at": "2026-10-01T10:00:00Z",
        "title": "[BOUNTY $20] Test deterministic source refresh",
        "body": "Acceptance criteria: real source readback before work.",
        "state": "open",
    }


class SnapshotRefreshTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        self.state = root / "state.json"
        self.sources = root / "sources.json"
        self.observations = root / "observations.ndjson"
        self.ledger = root / "run-ledger.ndjson"
        self.sources.write_text(json.dumps({
            "sources": [{"id": "github_public_demand", "enabled": True,
                         "adapter": "github_issue_search", "queries": ["one"]}]
        }), encoding="utf-8")
        self.write_state(0)

    def write_state(self, observed):
        self.state.write_text(json.dumps({
            "cycle": 0, "phase": "IDLE", "lease": {},
            "counters": {"observed": observed},
        }), encoding="utf-8")

    def put_previous(self, detected_at, item=None):
        previous = cycle.normalize(item or source_item(), "one", detected_at)
        self.observations.write_text(
            json.dumps(previous) + "\n", encoding="utf-8"
        )
        self.write_state(1)
        return previous

    def execute(self, at, response=None, error=None, direct_response=None):
        def search(query, token):
            if error is not None:
                raise error
            return [source_item()] if response is None else response

        def direct(url, token):
            if callable(direct_response):
                return direct_response(url)
            if direct_response is not None:
                return direct_response
            raise RuntimeError("synthetic_direct_readback_unavailable")

        with (
            patch.object(cycle, "STATE", self.state),
            patch.object(cycle, "SOURCES", self.sources),
            patch.object(cycle, "OBS", self.observations),
            patch.object(cycle, "RUNS", self.ledger),
            patch.object(cycle, "now", return_value=at),
            patch.object(cycle, "github_search", side_effect=search),
            patch.object(cycle, "github_issue_readback", side_effect=direct),
            patch.dict("os.environ", {"GITHUB_RUN_ID": "synthetic"}, clear=False),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(cycle.main(), 0)
        state = json.loads(self.state.read_text(encoding="utf-8"))
        rows = (
            [json.loads(line) for line in self.observations.read_text().splitlines()]
            if self.observations.exists() else []
        )
        ledger = [json.loads(line) for line in self.ledger.read_text().splitlines()]
        return state, rows, ledger

    def test_new_cycle_anchors_actual_archive_bytes_in_both_receipts(self):
        state, rows, ledger = self.execute(START)
        expected = hashlib.sha256(self.observations.read_bytes()).hexdigest()
        self.assertEqual(state["last_cycle_result"]["observations_sha256"], expected)
        self.assertEqual(ledger[-1]["observations_sha256"], expected)
        self.assertEqual(len(rows), 1)
        # A subsequent cycle with no appended observations still seals
        # the same archive bytes; the digest must not advance by itself.
        next_state, _, next_ledger = self.execute(START + timedelta(minutes=1))
        self.assertEqual(next_state["last_cycle_result"]["observations_sha256"], expected)
        self.assertEqual(next_ledger[-1]["observations_sha256"], expected)

    def test_empty_first_cycle_records_unambiguous_empty_archive_hash(self):
        state, rows, ledger = self.execute(START, response=[])
        empty = hashlib.sha256(b"").hexdigest()
        self.assertEqual(rows, [])
        self.assertEqual(state["last_cycle_result"]["observations_sha256"], empty)
        self.assertEqual(ledger[-1]["observations_sha256"], empty)

    def test_same_revision_old_readback_is_refreshed_not_new(self):
        prior = self.put_previous(cycle.iso(START))
        at = START + timedelta(days=6, minutes=1)
        state, rows, ledger = self.execute(at)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["fingerprint"], rows[1]["fingerprint"])
        self.assertEqual(rows[1]["detected_at"], cycle.iso(at))
        self.assertEqual(state["last_cycle_result"]["new_observations"], 0)
        self.assertEqual(state["last_cycle_result"]["refreshed_snapshots"], 1)
        self.assertEqual(state["counters"]["observed"], 2)
        self.assertEqual(ledger[0]["refreshed_snapshots"], 1)
        self.assertEqual(rows[0]["title"], prior["title"])

    def test_fresh_readback_not_copied_again(self):
        self.put_previous(cycle.iso(START))
        state, rows, ledger = self.execute(START + timedelta(days=5))
        self.assertEqual(len(rows), 1)
        self.assertEqual(state["counters"]["observed"], 1)
        self.assertEqual(state["last_cycle_result"]["refreshed_snapshots"], 0)
        self.assertEqual(ledger[0]["new_observations"], 0)

    def test_authenticated_github_api_redirect_cannot_leak_token(self):
        request = urllib.request.Request(
            "https://api.github.com/repos/example/repo/issues/320",
            headers={"Authorization": "Bearer SYNTHETIC_SECRET"},
        )
        handler = cycle.GitHubAPIRedirectOnly()
        for target in (
            "https://attacker.example/collect",
            "http://api.github.com/repos/example/repo/issues/320",
            "https://api.github.com.attacker.example/collect",
            "https://username:password@api.github.com/collect",
            "https://api.github.com:8443/repos/example/repo/issues/320",
            "https://127.0.0.1/collect",
        ):
            with self.subTest(target=target):
                for status in (301, 302, 307):
                    with self.assertRaisesRegex(
                        urllib.error.HTTPError, "unsafe_github_api_redirect"
                    ):
                        handler.redirect_request(request, None, status,
                                                 "Redirect", {}, target)
        approved = handler.redirect_request(
            request, None, 301, "Moved", {},
            "https://api.github.com/repos/example/newrepo/issues/320")
        self.assertEqual(approved.host, "api.github.com")
        self.assertEqual(approved.get_header("Authorization"),
                         "Bearer SYNTHETIC_SECRET")

    def test_authenticated_search_and_direct_readback_use_guarded_opener(self):
        seen = []
        def fake_open(request, timeout):
            seen.append((request.full_url, request.get_header("Authorization"), timeout))
            if "/search/issues" in request.full_url:
                result = {"items": [source_item()]}
            else:
                result = {"html_url": source_item()["html_url"], "number": 320,
                          "id": 320, "state": "open", "title": "Synthetic test",
                          "body": None, "updated_at": "2026-10-01T11:00:00Z"}
            return io.BytesIO(json.dumps(result).encode("utf-8"))

        with patch.object(cycle.GITHUB_API_OPENER, "open", side_effect=fake_open):
            found = cycle.github_search("test", "NOT_REAL_TOKEN")
            direct = cycle.github_issue_readback(source_item()["html_url"],
                                                 "NOT_REAL_TOKEN")
        self.assertEqual(found[0]["number"], 320)
        self.assertEqual(direct["number"], 320)
        self.assertEqual(len(seen), 2)
        self.assertTrue(all(item[0].startswith("https://api.github.com/")
                            for item in seen))
        self.assertTrue(all(item[1] == "Bearer NOT_REAL_TOKEN" for item in seen))

    def test_search_rejects_prs_and_invalid_hits_without_losing_real_issues(self):
        valid = source_item()
        malicious = [
            dict(valid, html_url="https://evil.example/exfiltrate"),
            dict(valid, pull_request={"url": "https://api.github.com/example"}),
            dict(valid, number=321),
            dict(valid, id=True),
            dict(valid, state="not-a-state"),
            {"html_url": None, "id": 42},
        ]
        state, rows, ledger = self.execute(
            START, response=malicious + [valid])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], valid["html_url"])
        self.assertEqual(state["last_cycle_result"]["new_observations"], 1)
        self.assertEqual(ledger[0]["new_observations"], 1)

    def test_unseen_revision_is_new_not_refresh(self):
        state, rows, ledger = self.execute(START)
        self.assertEqual(len(rows), 1)
        self.assertEqual(state["last_cycle_result"]["new_observations"], 1)
        self.assertEqual(state["last_cycle_result"]["refreshed_snapshots"], 0)
        self.assertEqual(ledger[0]["new_observations"], 1)

    def test_overlapping_queries_do_not_duplicate_refreshed_capture(self):
        self.put_previous(cycle.iso(START))
        self.sources.write_text(json.dumps({
            "sources": [{"id": "github_public_demand", "enabled": True,
                         "adapter": "github_issue_search", "queries": ["one", "two"]}]
        }), encoding="utf-8")
        state, rows, _ = self.execute(START + timedelta(days=7))
        self.assertEqual(len(rows), 2)
        self.assertEqual(state["last_cycle_result"]["refreshed_snapshots"], 1)

    def test_malformed_old_capture_is_refreshed_conservatively(self):
        self.put_previous("bad-timestamp")
        state, rows, _ = self.execute(START)
        self.assertEqual(len(rows), 2)
        self.assertEqual(state["last_cycle_result"]["refreshed_snapshots"], 1)

    def test_failed_fetch_never_manufactures_a_refresh(self):
        self.put_previous(cycle.iso(START))
        state, rows, ledger = self.execute(
            START + timedelta(days=7), error=RuntimeError("offline test error"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(state["last_cycle_result"]["refreshed_snapshots"], 0)
        self.assertEqual(state["last_cycle_result"]["source_errors"][0]["error"],
                         "RuntimeError")
        self.assertEqual(ledger[0]["new_observations"], 0)

    def test_stale_candidate_fallen_out_of_search_is_directly_recaptured(self):
        self.put_previous(cycle.iso(START))
        at = START + timedelta(days=8)
        state, rows, ledger = self.execute(
            at, response=[], direct_response=source_item()
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["source_state"], "open")
        self.assertFalse(rows[1]["primary_source_verified"])
        self.assertEqual(state["last_cycle_result"]["new_observations"], 0)
        self.assertEqual(state["last_cycle_result"]["refreshed_snapshots"], 1)
        self.assertEqual(state["last_cycle_result"]["direct_readback_attempts"], 1)
        self.assertEqual(state["last_cycle_result"]["direct_readback_captures"], 1)
        self.assertEqual(ledger[0]["direct_readback_captures"], 1)

    def test_closed_source_is_captured_but_held_from_verify(self):
        import triage

        self.put_previous(cycle.iso(START))
        closed = dict(source_item(), state="closed",
                      updated_at="2026-10-09T11:00:00Z")
        at = START + timedelta(days=8)
        state, rows, _ = self.execute(at, response=[], direct_response=closed)
        self.assertEqual(state["last_cycle_result"]["direct_readback_closed"], 1)
        self.assertEqual(len(rows), 2)
        latest = triage.newest_by_url(rows)[0]
        self.assertEqual(latest["source_state"], "closed")
        self.assertEqual(triage.classify(latest, at)["disposition"], "HOLD_SOURCE_CLOSED")

    def test_identity_mismatch_does_not_create_fake_readback(self):
        self.put_previous(cycle.iso(START))
        mismatched = dict(source_item(), id=777)
        state, rows, _ = self.execute(
            START + timedelta(days=8), response=[], direct_response=mismatched
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(state["last_cycle_result"]["direct_readback_attempts"], 1)
        self.assertEqual(state["last_cycle_result"]["direct_readback_captures"], 0)
        self.assertEqual(state["last_cycle_result"]["source_errors"][0]["error"], "ValueError")

    def test_at_most_three_direct_readbacks_per_cycle(self):
        observed = []
        available = {}
        for n in range(1, 6):
            record = dict(source_item(), id=n, number=n,
                          html_url=f"https://github.com/example/repo/issues/{n}")
            available[record["html_url"]] = record
            observed.append(cycle.normalize(record, "one", cycle.iso(START)))
        self.observations.write_text(
            "".join(json.dumps(x) + "\n" for x in observed), encoding="utf-8"
        )
        self.write_state(len(observed))
        calls = []
        def retrieve(url):
            calls.append(url)
            return available[url]
        state, rows, _ = self.execute(
            START + timedelta(days=8), response=[], direct_response=retrieve
        )
        self.assertEqual(state["last_cycle_result"]["direct_readback_attempts"], 3)
        self.assertEqual(state["last_cycle_result"]["direct_readback_captures"], 3)
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(rows), 8)

    def test_direct_issue_url_allowlist_prevents_external_fetch(self):
        for url in (
            "https://evil.example/issues/7",
            "https://github.com/owner/repo/pull/3",
            "https://github.com/owner/repo/issues/1?redirect=evil",
            "https://github.com/owner/repo/issues/0",
        ):
            with self.subTest(url=url), patch.object(cycle.urllib.request, "urlopen") as opener:
                with self.assertRaises(ValueError):
                    cycle.github_issue_readback(url, None)
                opener.assert_not_called()

    def test_failed_direct_readback_is_cooled_down_across_cycles(self):
        self.put_previous(cycle.iso(START))
        at = START + timedelta(days=8)
        state, rows, _ = self.execute(at, response=[])
        self.assertEqual(state["last_cycle_result"]["direct_readback_attempts"], 1)
        self.assertEqual(state["last_cycle_result"]["direct_readback_captures"], 0)
        self.assertEqual(len(rows), 1)

        second, same_rows, _ = self.execute(
            at + timedelta(hours=1), response=[], direct_response=source_item()
        )
        self.assertEqual(second["last_cycle_result"]["direct_readback_attempts"], 0)
        self.assertEqual(len(same_rows), 1)

        third, refreshed, _ = self.execute(
            at + timedelta(hours=25), response=[], direct_response=source_item()
        )
        self.assertEqual(third["last_cycle_result"]["direct_readback_attempts"], 1)
        self.assertEqual(third["last_cycle_result"]["direct_readback_captures"], 1)
        self.assertEqual(len(refreshed), 2)

    def test_http_error_status_is_diagnostic_not_a_fresh_capture(self):
        import urllib.error

        self.put_previous(cycle.iso(START))
        def unavailable(url):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

        state, rows, ledger = self.execute(
            START + timedelta(days=8), response=[], direct_response=unavailable
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(state["last_cycle_result"]["direct_readback_captures"], 0)
        problem = state["last_cycle_result"]["source_errors"][0]
        self.assertEqual(problem["http_status"], 404)
        self.assertEqual(problem["error"], "HTTPError")
        self.assertEqual(ledger[0]["errors"][0]["http_status"], 404)

    def test_second_cycle_does_not_repeat_a_recent_refresh(self):
        self.put_previous(cycle.iso(START))
        at = START + timedelta(days=7)
        self.execute(at)
        state, rows, _ = self.execute(at + timedelta(minutes=1))
        self.assertEqual(len(rows), 2)
        self.assertEqual(state["last_cycle_result"]["refreshed_snapshots"], 0)
        self.assertEqual(state["counters"]["observed"], 2)


class StaleReachabilityRegressions(unittest.TestCase):
    """Real ledger shape, synthetic source responses; no GitHub I/O."""

    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        self.obs = root / "observations.ndjson"
        self.ledger = root / "run-ledger.ndjson"
        self.current = START + timedelta(days=8)
        self.rows = []
        for number in range(1, 6):
            item = dict(source_item(), id=number, number=number,
                        html_url=f"https://github.com/example/repo/issues/{number}")
            self.rows.append(cycle.normalize(item, "one", cycle.iso(START)))
        self.obs.write_text("".join(json.dumps(row) + "\n" for row in self.rows))
        self.ledger.write_text("")
        self.known = {row["fingerprint"]: START for row in self.rows}

    def append_failure(self, numbers, at):
        row = {
            "at": cycle.iso(at),
            "result": "SENSE_COMPLETE",
            "errors": [
                {"source": "github_direct_readback",
                 "url": f"https://github.com/example/repo/issues/{number}",
                 "error": "HTTPError", "http_status": 404}
                for number in numbers
            ],
        }
        with self.ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")

    def choose(self):
        with (patch.object(cycle, "OBS", self.obs),
              patch.object(cycle, "RUNS", self.ledger)):
            selected = cycle.select_direct_readbacks(self.current, self.known, set())
            recent = cycle.recent_failed_direct_readbacks(self.current)
        return [int(row["url"].rsplit("/", 1)[1]) for row in selected], recent

    def test_without_failure_history_preserves_existing_score_and_url_order(self):
        selected, recent = self.choose()
        self.assertEqual(selected, [1, 2, 3, 4, 5])
        self.assertEqual(recent, set())

    def test_expired_404_does_not_starve_untried_stale_sources(self):
        # Recorded attempts are 25h old: existing 24h cooldown has expired.
        self.append_failure([1, 2], self.current - timedelta(hours=25))
        selected, recent = self.choose()
        self.assertEqual(recent, set())
        self.assertEqual(selected[:3], [3, 4, 5])
        self.assertEqual(set(selected), {1, 2, 3, 4, 5})
        self.assertEqual(cycle.MAX_DIRECT_READBACKS, 3)
        self.assertTrue(all(row["primary_source_verified"] is False
                            and row["realized_value"] == 0 for row in self.rows))

    def test_earlier_failures_win_over_more_recent_failures_after_expiry(self):
        self.append_failure([1, 2, 3, 4, 5], self.current - timedelta(days=3))
        self.append_failure([1], self.current - timedelta(hours=25))
        selected, _ = self.choose()
        self.assertEqual(selected, [2, 3, 4, 5, 1])

    def test_recent_cooldown_and_future_receipt_still_fail_closed(self):
        self.append_failure([1], self.current - timedelta(hours=1))
        self.append_failure([2], self.current + timedelta(hours=2))
        selected, recent = self.choose()
        self.assertEqual(selected, [2, 3, 4, 5, 1])
        self.assertEqual(recent, {"https://github.com/example/repo/issues/1"})
        self.assertNotIn("https://github.com/example/repo/issues/2", recent)


if __name__ == "__main__":
    unittest.main()
