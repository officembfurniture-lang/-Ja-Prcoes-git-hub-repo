"""Offline, deterministic regressions for source-revision snapshot refresh.

All GitHub responses and clock readings are synthetic. No network or paid work.
"""
from __future__ import annotations

import contextlib
import io
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
        "html_url": "https://github.com/example/repo/issues/320",
        "updated_at": "2026-10-01T11:00:00Z",
        "created_at": "2026-10-01T10:00:00Z",
        "title": "[BOUNTY $20] Test deterministic source refresh",
        "body": "Acceptance criteria: real source readback before work.",
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

    def execute(self, at, response=None, error=None):
        def search(query, token):
            if error is not None:
                raise error
            return [source_item()] if response is None else response

        with (
            patch.object(cycle, "STATE", self.state),
            patch.object(cycle, "SOURCES", self.sources),
            patch.object(cycle, "OBS", self.observations),
            patch.object(cycle, "RUNS", self.ledger),
            patch.object(cycle, "now", return_value=at),
            patch.object(cycle, "github_search", side_effect=search),
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

    def test_second_cycle_does_not_repeat_a_recent_refresh(self):
        self.put_previous(cycle.iso(START))
        at = START + timedelta(days=7)
        self.execute(at)
        state, rows, _ = self.execute(at + timedelta(minutes=1))
        self.assertEqual(len(rows), 2)
        self.assertEqual(state["last_cycle_result"]["refreshed_snapshots"], 0)
        self.assertEqual(state["counters"]["observed"], 2)


if __name__ == "__main__":
    unittest.main()
