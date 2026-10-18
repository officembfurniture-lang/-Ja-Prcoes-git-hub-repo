"""Synthetic tests for bounded, deterministic feedback choices."""
import unittest

from feedback import recommend


class FeedbackTests(unittest.TestCase):
    def test_settlement_takes_priority(self):
        result = recommend({"diagnostic_alerts": ["no_verified_conversion", "unsettled_acceptances"], "verified": 0, "delivered": 0})
        self.assertEqual(result["focus"], "VERIFY_SETTLEMENT")
        self.assertFalse(result["authorization_granted"])
        self.assertFalse(result["external_action_taken"])

    def test_settlement_priority_preserves_parallel_sensor_failure(self):
        result = recommend({
            "diagnostic_alerts": ["unsettled_acceptances", "zero_direct_readback_captures"],
            "verified": 2,
            "delivered": 2,
            "last_sensor_direct_readback_attempts": 3,
            "last_sensor_direct_readback_captures": 0,
            "last_sensor_direct_readback_http_404s": 3,
        })
        self.assertEqual(result["focus"], "VERIFY_SETTLEMENT")
        self.assertEqual(len(result["secondary_diagnostics"]), 1)
        diagnostic = result["secondary_diagnostics"][0]
        self.assertEqual(diagnostic["code"], "DIRECT_READBACK_ZERO_CAPTURE_ALL_404")
        self.assertEqual(diagnostic["observed"], {"attempts": 3, "captures": 0, "http_404s": 3})
        self.assertIn("do not retry the same failed URL", diagnostic["next_action"])
        self.assertIn("does not by itself prove deletion", diagnostic["evidence_boundary"])
        self.assertFalse(result["authorization_granted"])
        self.assertFalse(result["external_action_taken"])

    def test_partial_404_chain_is_visible_even_with_a_successful_capture(self):
        result = recommend({
            "diagnostic_alerts": ["direct_readback_http_404"],
            "verified": 2,
            "delivered": 2,
            "last_sensor_direct_readback_attempts": 3,
            "last_sensor_direct_readback_captures": 1,
            "last_sensor_direct_readback_http_404s": 2,
        })
        self.assertEqual(result["focus"], "MAINTAIN_AND_MEASURE")
        self.assertEqual(len(result["secondary_diagnostics"]), 1)
        diagnostic = result["secondary_diagnostics"][0]
        self.assertEqual(diagnostic["code"], "DIRECT_READBACK_404_RETRY_CHAIN")
        self.assertIn("six-day snapshot TTL", diagnostic["next_action"])
        self.assertIn("stale closed snapshots", diagnostic["next_action"])
        self.assertIn("does not by itself prove deletion", diagnostic["evidence_boundary"])
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
