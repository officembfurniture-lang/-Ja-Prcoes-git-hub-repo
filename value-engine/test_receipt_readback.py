import json
import unittest
from pathlib import Path

from receipt_readback import verify_wallet_readback


ROOT = Path(__file__).parent
CAPTURE = json.loads((ROOT / "evidence/rustchain-wallet-readback-2026-11-20.json").read_text())
OUTCOMES = [json.loads(line) for line in (ROOT / "outcomes.ndjson").read_text().splitlines()]


class ReceiptReadbackTests(unittest.TestCase):
    def test_capture_matches_two_historical_payment_rows(self):
        result = verify_wallet_readback(CAPTURE, OUTCOMES)
        self.assertEqual(result["summary"]["matched_confirmed_payments"], 2)
        self.assertEqual(result["summary"]["fiat_cash_total"], 0)
        self.assertFalse(result["authoritative"])
        self.assertFalse(result["production_policy_update"])

    def test_acceptance_attribution_is_not_collapsed_into_payment(self):
        result = verify_wallet_readback(CAPTURE, OUTCOMES)
        by_id = {row["opportunity_id"]: row for row in result["results"]}
        self.assertEqual(
            by_id["Scottcjn/rustchain-bounties#13949"]["acceptance_attribution"],
            "PUBLIC_ACCEPTANCE_CHAIN_FOUND")
        self.assertEqual(
            by_id["Scottcjn/rustchain-bounties#1102:bottube-agents-search"]["acceptance_attribution"],
            "PUBLIC_ACCEPTANCE_CHAIN_UNRESOLVED")

    def test_modified_capture_fails_digest_check(self):
        altered = json.loads(json.dumps(CAPTURE))
        altered["response"]["transactions"][0]["amount"] = 500
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            verify_wallet_readback(altered, OUTCOMES)

    def test_wrong_outcome_amount_is_not_counted(self):
        altered = [dict(row) for row in OUTCOMES]
        altered[0]["amount"] = 200
        result = verify_wallet_readback(CAPTURE, altered)
        self.assertEqual(result["summary"]["matched_confirmed_payments"], 1)
        self.assertIn("amount", result["results"][0]["checks"])
        self.assertFalse(result["results"][0]["checks"]["amount"])

    def test_duplicate_transaction_hash_fails_closed(self):
        altered = json.loads(json.dumps(CAPTURE))
        altered["response"]["transactions"].append(
            dict(altered["response"]["transactions"][0]))
        altered["response"]["total"] += 1
        # The response digest must be updated to isolate duplicate-hash validation.
        import hashlib
        canonical = json.dumps(altered["response"], sort_keys=True,
                               separators=(",", ":"), ensure_ascii=False).encode()
        altered["canonical_response_sha256"] = hashlib.sha256(canonical).hexdigest()
        with self.assertRaisesRegex(ValueError, "duplicate transaction hash"):
            verify_wallet_readback(altered, OUTCOMES)


if __name__ == "__main__":
    unittest.main()
