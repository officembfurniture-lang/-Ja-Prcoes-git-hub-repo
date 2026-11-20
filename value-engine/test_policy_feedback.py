import unittest

from policy_feedback import build_shadow_feedback


def verification_claim():
    return {
        "status": "INDEPENDENTLY_VERIFIED",
        "verifier": "untrusted-caller-claim",
        "method": "public_settlement_record",
        "evidence_uri": "https://example.invalid/settlement/1",
        "evidence_sha256": "a" * 64,
        "verified_at": "2026-01-02T00:00:00Z",
        "verification_record_uri": "https://example.invalid/verification/1",
        "verification_record_sha256": "b" * 64,
    }


def outcome_claim(**overrides):
    row = {
        "receipt_id": "claim-1",
        "settlement_status": "PAID",
        "source_family": "source-A",
        "opportunity_class": "funded_task",
        "amount": 5,
        "currency": "RTC",
        "received_at": "2026-01-01T00:00:00Z",
        "verification": verification_claim(),
    }
    row.update(overrides)
    return row


class PolicyFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.candidates = [
            {"candidate_id": "b", "source_family": "source-B", "base_rank": 1},
            {"candidate_id": "a", "source_family": "source-A", "base_rank": 1},
        ]

    def test_structurally_valid_claim_changes_only_shadow_tie_break(self):
        result = build_shadow_feedback(
            [outcome_claim(source_family="source-B")], self.candidates, "frozen-input-v1")
        self.assertEqual(result["baseline_order"], ["a", "b"])
        self.assertEqual(result["shadow_order"], ["b", "a"])
        self.assertTrue(result["decision_changed"])
        self.assertFalse(result["policy_mutated"])
        self.assertFalse(result["authoritative"])
        self.assertFalse(result["caller_supplied_claims_are_authenticated"])

    def test_claim_without_independent_verification_statement_is_rejected(self):
        row = outcome_claim(verification={**verification_claim(), "status": "UNVERIFIED"})
        result = build_shadow_feedback([row], self.candidates, "frozen-input-v1")
        self.assertEqual(result["shadow_order"], result["baseline_order"])
        self.assertEqual(result["rejected_claims"][0]["reason"],
                         "NO_INDEPENDENT_VERIFICATION_CLAIM")

    def test_malformed_hash_is_rejected(self):
        row = outcome_claim(verification={**verification_claim(), "evidence_sha256": "bad"})
        result = build_shadow_feedback([row], self.candidates, "frozen-input-v1")
        self.assertEqual(result["shadow_order"], result["baseline_order"])
        self.assertEqual(result["rejected_claims"][0]["reason"],
                         "INVALID_EVIDENCE_SHA256")

    def test_not_paid_claim_cannot_create_preference(self):
        result = build_shadow_feedback(
            [outcome_claim(settlement_status="ACCEPTED")], self.candidates, "frozen-input-v1")
        self.assertEqual(result["shadow_order"], result["baseline_order"])
        self.assertEqual(result["rejected_claims"][0]["reason"], "NOT_CLAIMED_PAID")

    def test_all_copies_of_duplicate_claim_id_are_rejected(self):
        first = outcome_claim(source_family="source-A")
        second = outcome_claim(source_family="source-B")
        result = build_shadow_feedback([first, second], self.candidates, "frozen-input-v1")
        self.assertEqual(result["eligible_untrusted_claim_ids"], [])
        self.assertEqual(result["source_family_claim_counts"], {})
        self.assertEqual([x["reason"] for x in result["rejected_claims"]],
                         ["DUPLICATE_CLAIM_ID", "DUPLICATE_CLAIM_ID"])

    def test_replay_is_deterministic_and_input_bound(self):
        first = build_shadow_feedback([outcome_claim()], self.candidates, "frozen-input-v1")
        second = build_shadow_feedback([outcome_claim()], self.candidates, "frozen-input-v1")
        changed = build_shadow_feedback([outcome_claim()], self.candidates, "frozen-input-v2")
        self.assertEqual(first, second)
        self.assertNotEqual(first["input_sha256"], changed["input_sha256"])

    def test_no_claims_means_no_ranking_delta(self):
        result = build_shadow_feedback([], self.candidates, "frozen-input-v1")
        self.assertEqual(result["shadow_order"], result["baseline_order"])
        self.assertFalse(result["decision_changed"])
        self.assertEqual(result["proposed_source_family_preference"], [])

    def test_non_finite_claim_amounts_fail_closed(self):
        for amount in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(amount=amount):
                with self.assertRaisesRegex(ValueError, "finite JSON-compatible"):
                    build_shadow_feedback(
                        [outcome_claim(amount=amount)], self.candidates, "frozen-input-v1")

    def test_malformed_candidates_fail_closed_with_clear_error(self):
        cases = [
            ([], "CANDIDATES_MUST_BE_NONEMPTY_LIST"),
            ([{"candidate_id": "a", "source_family": "x"}], "CANDIDATE_BASE_RANK_INVALID"),
            ([{"candidate_id": "a", "source_family": "x", "base_rank": True}],
             "CANDIDATE_BASE_RANK_INVALID"),
            ([{"candidate_id": "a", "source_family": "x", "base_rank": 1},
              {"candidate_id": "a", "source_family": "y", "base_rank": 1}],
             "DUPLICATE_CANDIDATE_ID"),
        ]
        for candidates, expected in cases:
            with self.subTest(candidates=candidates):
                with self.assertRaisesRegex(ValueError, expected):
                    build_shadow_feedback([], candidates, "frozen-input-v1")

    def test_non_json_and_nonfinite_candidate_input_fails_closed(self):
        candidates = [{"candidate_id": "a", "source_family": "x", "base_rank": 1,
                       "extra": float("nan")}]
        with self.assertRaisesRegex(ValueError, "finite JSON-compatible"):
            build_shadow_feedback([], candidates, "frozen-input-v1")

    def test_naive_received_at_is_rejected(self):
        result = build_shadow_feedback(
            [outcome_claim(received_at="2026-01-01T00:00:00")],
            self.candidates, "frozen-input-v1")
        self.assertEqual(result["rejected_claims"][0]["reason"], "INVALID_RECEIVED_AT")

    def test_naive_verified_at_is_rejected(self):
        claim = outcome_claim()
        claim["verification"]["verified_at"] = "2026-01-02T00:00:00"
        result = build_shadow_feedback([claim], self.candidates, "frozen-input-v1")
        self.assertEqual(result["rejected_claims"][0]["reason"], "INVALID_VERIFIED_AT")


if __name__ == "__main__":
    unittest.main()
