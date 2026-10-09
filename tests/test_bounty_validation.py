"""Regression tests for strict BOUNTY_ENGINE state/ledger validation."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "bounty-engine" / "validate_state.py"
SPEC = importlib.util.spec_from_file_location("repo_bounty_validate_state", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load bounty validator")
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


def valid_state():
    return {
        "engine": "BOUNTY_ENGINE_v1",
        "cycle": 1,
        "state": "IDLE",
        "active_bounty": None,
        "realized_value_usd": 0,
        "submitted": 0,
        "accepted": 0,
        "paid": 0,
        "human_gates": 0,
    }


class BountyValidationTests(unittest.TestCase):
    def validate_fixture(self, state, rows=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "state.json").write_text(json.dumps(state), encoding="utf-8")
            (root / "ledger.ndjson").write_text(
                "".join(json.dumps(row) + "\n" for row in (rows or [])),
                encoding="utf-8",
            )
            validator.validate(root)

    def test_valid_idle_state_passes(self):
        self.validate_fixture(valid_state())

    def test_boolean_counter_is_rejected(self):
        state = valid_state()
        state["submitted"] = True
        with self.assertRaises(AssertionError):
            self.validate_fixture(state)

    def test_nonfinite_realized_value_is_rejected(self):
        state = valid_state()
        state["realized_value_usd"] = float("nan")
        with self.assertRaises(AssertionError):
            self.validate_fixture(state)

    def test_ledger_flags_must_be_boolean(self):
        with self.assertRaises(AssertionError):
            self.validate_fixture(valid_state(), [{"submitted": "false", "realized_value_usd": 0}])

    def test_state_cannot_understate_explicit_paid_ledger_event(self):
        row = {
            "submitted": True,
            "accepted": True,
            "paid": True,
            "realized_value_usd": 1,
        }
        with self.assertRaises(AssertionError):
            self.validate_fixture(valid_state(), [row])


if __name__ == "__main__":
    unittest.main()
