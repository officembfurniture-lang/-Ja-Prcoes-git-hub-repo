"""Offline regressions for exact sensor workflow_run handoff provenance."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sensor_handoff as handoff


RUN_ID = 38103192809
CYCLE_ID = f"cycle-234-{RUN_ID}"
STAMP = "2026-10-11T01:50:56Z"
HEAD_NEW = "a" * 40
HEAD_OLD = "b" * 40


def matching_state(run_id=RUN_ID):
    return {
        "cycle": 234,
        "phase": "IDLE",
        "lease": {"cycle_id": None, "owner": None},
        "last_cycle_result": {
            "cycle_id": f"cycle-234-{run_id}",
            "at": STAMP,
            "new_observations": 46,
            "refreshed_snapshots": 0,
            "direct_readback_attempts": 3,
            "direct_readback_captures": 0,
            "direct_readback_closed": 0,
            "source_errors": [],
            "selected": 0,
            "delivered": 0,
            "paid": 0,
        },
    }


def matching_ledger(run_id=RUN_ID):
    return {
        "cycle_id": f"cycle-234-{run_id}",
        "at": STAMP,
        "result": "SENSE_COMPLETE",
        "new_observations": 46,
        "refreshed_snapshots": 0,
        "direct_readback_attempts": 3,
        "direct_readback_captures": 0,
        "direct_readback_closed": 0,
        "errors": [],
        "realized_value": 0,
    }


class HandoffTests(unittest.TestCase):
    def test_exact_run_and_ledger_agree(self):
        self.assertTrue(handoff.matches_sensor(
            matching_state(), matching_ledger(), RUN_ID))

    def test_wrong_run_and_broken_reconciliation_fail_closed(self):
        self.assertFalse(handoff.matches_sensor(
            matching_state(), matching_ledger(), RUN_ID + 1))
        for field, value in (
            ("at", "2026-10-11T02:01:00Z"),
            ("new_observations", 47),
            ("refreshed_snapshots", True),
            ("result", "SENSE_FAILED"),
            ("realized_value", 1),
            ("errors", [{"error": "HTTPError"}]),
        ):
            ledger = matching_ledger()
            ledger[field] = value
            with self.subTest(field=field):
                self.assertFalse(handoff.matches_sensor(
                    matching_state(), ledger, RUN_ID))
        state = matching_state()
        state["phase"] = "PRODUCE"
        self.assertFalse(handoff.matches_sensor(state, matching_ledger(), RUN_ID))

    def test_locates_prior_matching_commit_not_moving_main_head(self):
        old_state = matching_state()
        new_state = matching_state(RUN_ID + 1)
        files = {
            f"{HEAD_NEW}:{handoff.STATE_PATH}": json.dumps(new_state),
            f"{HEAD_OLD}:{handoff.STATE_PATH}": json.dumps(old_state),
            f"{HEAD_OLD}:{handoff.LEDGER_PATH}": json.dumps(matching_ledger()) + "\n",
        }
        calls = []
        def fake_git(root, *args):
            calls.append(args)
            if args[0] == "rev-list":
                self.assertEqual(args[1], "--max-count=256")
                self.assertEqual(args[2], "origin/main")
                return HEAD_NEW + "\n" + HEAD_OLD + "\n"
            if args[0] == "show":
                return files[args[1]]
            self.fail("unexpected git subcommand")
        with patch.object(handoff, "git_text", side_effect=fake_git):
            found = handoff.locate_sensor_commit(Path("/synthetic"), RUN_ID)
        self.assertEqual(found, HEAD_OLD)
        self.assertIn(("show", f"{HEAD_OLD}:{handoff.LEDGER_PATH}"), calls)

    def test_matching_cycle_with_mismatched_ledger_stops_without_fallback(self):
        content = {
            f"{HEAD_NEW}:{handoff.STATE_PATH}": json.dumps(matching_state()),
            f"{HEAD_NEW}:{handoff.LEDGER_PATH}": json.dumps(matching_ledger(RUN_ID + 1)),
        }
        def fake_git(root, *args):
            if args[0] == "rev-list":
                return HEAD_NEW + "\n" + HEAD_OLD + "\n"
            return content[args[1]]
        with patch.object(handoff, "git_text", side_effect=fake_git):
            with self.assertRaisesRegex(ValueError, "mismatch"):
                handoff.locate_sensor_commit(Path("/synthetic"), RUN_ID)

    def test_missing_or_out_of_window_cycle_has_no_fallback(self):
        with patch.object(handoff, "git_text", return_value=HEAD_NEW + "\n"):
            with self.assertRaisesRegex(ValueError, "no safely matched"):
                handoff.locate_sensor_commit(Path("/synthetic"), RUN_ID)

    def test_non_positive_and_boolean_run_ids_are_rejected(self):
        for value in (0, -1, True, "38103192809"):
            with self.subTest(value=value):
                self.assertFalse(handoff.matches_sensor(
                    matching_state(), matching_ledger(), value))
                with self.assertRaises(ValueError):
                    handoff.locate_sensor_commit(Path("/synthetic"), value)

    def test_last_ledger_record_uses_last_not_earlier_receipt(self):
        good = matching_ledger()
        bad = matching_ledger(RUN_ID + 1)
        latest = handoff.last_ledger_record(
            json.dumps(good) + "\n\n" + json.dumps(bad) + "\n")
        self.assertEqual(latest["cycle_id"], bad["cycle_id"])
        with self.assertRaises(ValueError):
            handoff.last_ledger_record("")


if __name__ == "__main__":
    unittest.main()
