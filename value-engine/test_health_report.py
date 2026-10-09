"""Synthetic regression tests for the read-only health report."""
import json
import tempfile
import unittest
from pathlib import Path

import health_report


class HealthReportTests(unittest.TestCase):
    def test_report_does_not_modify_state_or_infer_cash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = {
                "engine": "VALUE_ENGINE_v2", "cycle": 7, "phase": "IDLE",
                "counters": {"observed": 50, "verified": 3, "delivered": 2,
                             "accepted": 2, "paid": 0},
                "realized": {"cash": []},
                "last_cycle_result": {"new_observations": 10},
            }
            path = root / "state.json"
            original = json.dumps(state)
            path.write_text(original, encoding="utf-8")
            report = health_report.build(root)
            self.assertEqual(report["accepted_without_verified_payment"], 2)
            self.assertEqual(report["cash_receipt_count"], 0)
            self.assertIn("unsettled_acceptances", report["diagnostic_alerts"])
            self.assertIsNone(report["external_cash_amount"])
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_paid_count_reduces_unsettled_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "state.json").write_text(json.dumps({
                "engine": "VALUE_ENGINE_v2", "cycle": 8, "phase": "IDLE",
                "counters": {"observed": 20, "verified": 3, "delivered": 2,
                             "accepted": 2, "paid": 1},
                "realized": {"cash": [{"amount": 1, "currency": "TEST"}]},
            }), encoding="utf-8")
            report = health_report.build(root)
            self.assertEqual(report["accepted_without_verified_payment"], 1)
            self.assertIn("unsettled_acceptances", report["diagnostic_alerts"])
            self.assertIsNone(report["external_cash_amount"])


if __name__ == "__main__":
    unittest.main()
