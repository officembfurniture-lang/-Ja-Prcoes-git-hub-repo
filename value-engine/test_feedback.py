"""Synthetic tests for bounded, deterministic feedback choices."""
import unittest

from feedback import recommend


class FeedbackTests(unittest.TestCase):
    def test_settlement_takes_priority(self):
        result = recommend({"diagnostic_alerts": ["no_verified_conversion", "unsettled_acceptances"], "verified": 0, "delivered": 0})
        self.assertEqual(result["focus"], "VERIFY_SETTLEMENT")
        self.assertFalse(result["authorization_granted"])
        self.assertFalse(result["external_action_taken"])

    def test_source_quality_when_no_verified_opportunities(self):
        self.assertEqual(recommend({"diagnostic_alerts": ["no_verified_conversion"]})["focus"], "REVIEW_SOURCE_QUALITY")

    def test_delivery_gap(self):
        self.assertEqual(recommend({"verified": 3, "delivered": 1})["focus"], "REVIEW_DELIVERY_ROUTES")

    def test_feedback_is_deterministic_and_non_authorizing(self):
        report = {"diagnostic_alerts": ["unsettled_acceptances"], "verified": 2, "delivered": 2}
        first = recommend(report)
        self.assertEqual(first, recommend(report))
        self.assertEqual(first["mode"], "ADVISORY_ONLY")
        self.assertFalse(first["authorization_granted"])
        self.assertFalse(first["external_action_taken"])

    def test_no_gap_does_not_manufacture_progress(self):
        self.assertEqual(recommend({"verified": 2, "delivered": 2})["focus"], "MAINTAIN_AND_MEASURE")


if __name__ == "__main__":
    unittest.main()
