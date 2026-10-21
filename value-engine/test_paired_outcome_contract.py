"""Contract tests only; synthetic cases are not evidence of effectiveness."""
import unittest

from paired_outcome_contract import assess


def report():
    return {
        "schema": "paired-outcome-report/v1",
        "candidate_operator": "operator-A",
        "pairs": [{
            "frozen_input_sha256": "a" * 64,
            "baseline": {"decision": "HOLD"},
            "candidate": {"decision": "PROCEED"},
            "independent_outcome": {
                "verified": True,
                "evidence_url": "https://example.org/evidence",
                "verified_by": "reviewer-B",
                "candidate_better_than_baseline": True,
            },
            "correction_burden": {"measured": True, "baseline": 3, "candidate": 2},
        }],
    }


class PairedOutcomeContractTests(unittest.TestCase):
    def test_complete_pair_is_only_ready_for_external_adjudication(self):
        result = assess(report())
        self.assertEqual(result["status"], "READY_FOR_EXTERNAL_ADJUDICATION")
        self.assertFalse(result["promotion"])

    def test_missing_or_unfrozen_input_fails_closed(self):
        r = report()
        r["pairs"][0]["frozen_input_sha256"] = "not-frozen"
        self.assertEqual(assess(r)["status"], "HOLD")

    def test_unknown_outcome_or_burden_stays_hold(self):
        for section, key, value in (
            ("independent_outcome", "verified", False),
            ("correction_burden", "measured", False),
        ):
            with self.subTest(section=section):
                r = report()
                r["pairs"][0][section][key] = value
                self.assertEqual(assess(r)["status"], "HOLD")

    def test_same_decision_is_not_material_delta(self):
        r = report()
        r["pairs"][0]["candidate"]["decision"] = "HOLD"
        self.assertEqual(assess(r)["status"], "HOLD")

    def test_increased_correction_burden_is_regression_even_with_benefit(self):
        r = report()
        r["pairs"][0]["correction_burden"]["candidate"] = 4
        result = assess(r)
        self.assertEqual(result["status"], "DRIVER_REGRESSION")
        self.assertFalse(result["promotion"])

    def test_self_review_does_not_establish_independence(self):
        r = report()
        r["pairs"][0]["independent_outcome"]["verified_by"] = "operator-A"
        self.assertEqual(assess(r)["status"], "HOLD")

    def test_invalid_locator_does_not_pass(self):
        r = report()
        r["pairs"][0]["independent_outcome"]["evidence_url"] = "fixture://made-up"
        self.assertEqual(assess(r)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
