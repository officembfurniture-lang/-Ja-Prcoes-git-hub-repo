import unittest

from policy_feedback import build_shadow_feedback


def attestation():
    return {
        "status": "INDEPENDENTLY_VERIFIED",
        "verifier": "independent-test-verifier",
        "method": "public_settlement_record",
        "evidence_uri": "https://example.invalid/settlement/1",
        "evidence_sha256": "a" * 64,
        "verified_at": "2026-01-02T00:00:00Z",
        "verification_record_uri": "https://example.invalid/verification/1",
        "verification_record_sha256": "b" * 64,
    }


def receipt(**overrides):
    row = {
        "receipt_id": "receipt-1",
        "settlement_status": "PAID",
        "source_family": "source-A",
        "opportunity_class": "funded_task",
        "amount": 5,
        "currency": "RTC",
        "received_at": "2026-01-01T00:00:00Z",
        "verification": attestation(),
    }
    row.update(overrides)
    return row


class PolicyFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.candidates = [
            {"candidate_id": "b", "source_family": "source-B", "base_rank": 1},
            {"candidate_id": "a", "source_family": "source-A", "base_rank": 1},
        ]

    def test_verified_paid_receipt_changes_tied_shadow_selection(self):
        result = build_shadow_feedback([receipt(source_family="source-B")], self.candidates, "frozen-input-v1")
        self.assertEqual(result["baseline_order"], ["a", "b"])
        self.assertEqual(result["shadow_order"], ["b", "a"])
        self.assertTrue(result["decision_changed"])
        self.assertFalse(result["policy_mutated"])
        self.assertFalse(result["authoritative"])

    def test_unverified_receipt_cannot_change_policy_candidate(self):
        row = receipt(verification={**attestation(), "status": "UNVERIFIED"})
        result = build_shadow_feedback([row], self.candidates, "frozen-input-v1")
        self.assertEqual(result["shadow_order"], result["baseline_order"])
        self.assertFalse(result["decision_changed"])
        self.assertEqual(result["rejected_receipts"][0]["reason"],
                         "NOT_INDEPENDENTLY_VERIFIED")

    def test_missing_hash_or_provenance_fails_closed(self):
        row = receipt(verification={**attestation(), "evidence_sha256": "bad"})
        result = build_shadow_feedback([row], self.candidates, "frozen-input-v1")
        self.assertEqual(result["shadow_order"], result["baseline_order"])
        self.assertEqual(result["rejected_receipts"][0]["reason"],
                         "EVIDENCE_HASH_INVALID")

    def test_not_paid_cannot_create_preference(self):
        result = build_shadow_feedback(
            [receipt(settlement_status="ACCEPTED")], self.candidates, "frozen-input-v1")
        self.assertEqual(result["shadow_order"], result["baseline_order"])
        self.assertEqual(result["rejected_receipts"][0]["reason"], "NOT_PAID")

    def test_duplicate_receipt_is_counted_once(self):
        row = receipt()
        duplicate = {**row}
        result = build_shadow_feedback([row, duplicate], self.candidates, "frozen-input-v1")
        self.assertEqual(result["source_family_counts"], {"source-A": 1})
        self.assertEqual(result["rejected_receipts"][0]["reason"], "DUPLICATE_RECEIPT")

    def test_replay_is_deterministic_and_input_bound(self):
        first = build_shadow_feedback([receipt()], self.candidates, "frozen-input-v1")
        second = build_shadow_feedback([receipt()], self.candidates, "frozen-input-v1")
        changed = build_shadow_feedback([receipt()], self.candidates, "frozen-input-v2")
        self.assertEqual(first, second)
        self.assertNotEqual(first["input_sha256"], changed["input_sha256"])

    def test_no_receipts_means_no_policy_delta(self):
        result = build_shadow_feedback([], self.candidates, "frozen-input-v1")
        self.assertEqual(result["shadow_order"], result["baseline_order"])
        self.assertFalse(result["decision_changed"])
        self.assertEqual(result["proposed_source_family_preference"], [])


if __name__ == "__main__":
    unittest.main()
