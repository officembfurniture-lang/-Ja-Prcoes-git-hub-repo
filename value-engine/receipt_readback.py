"""Verify captured public wallet readbacks against the historical outcome ledger.

This is deterministic validation of a saved API response, not a live API client,
cryptographic proof of the ledger operator, or authority to update production policy.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def _utc_iso(epoch: Any) -> str | None:
    if not isinstance(epoch, int) or isinstance(epoch, bool):
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def verify_wallet_readback(capture: dict[str, Any],
                           outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(capture, dict) or not isinstance(outcomes, list):
        raise ValueError("capture must be an object and outcomes must be a list")
    source = capture.get("source", {})
    response = capture.get("response", {})
    if source.get("kind") != "public_wallet_history_api":
        raise ValueError("unsupported capture source")
    if response.get("ok") is not True:
        raise ValueError("wallet API response is not successful")
    wallet = source.get("wallet_id")
    if not isinstance(wallet, str) or not wallet:
        raise ValueError("wallet_id missing")
    transactions = response.get("transactions")
    if not isinstance(transactions, list) or response.get("total") != len(transactions):
        raise ValueError("wallet transaction count mismatch")

    canonical = json.dumps(response, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode("utf-8")
    actual_digest = hashlib.sha256(canonical).hexdigest()
    if capture.get("canonical_response_sha256") != actual_digest:
        raise ValueError("canonical response SHA-256 mismatch")

    by_hash: dict[str, dict[str, Any]] = {}
    for tx in transactions:
        if not isinstance(tx, dict):
            raise ValueError("transaction row must be an object")
        tx_hash = tx.get("tx_hash")
        if not isinstance(tx_hash, str) or not tx_hash or tx_hash in by_hash:
            raise ValueError("missing or duplicate transaction hash")
        by_hash[tx_hash] = tx

    results = []
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            raise ValueError("outcome row must be an object")
        tx_hash = outcome.get("payment_tx_hash")
        tx = by_hash.get(tx_hash)
        if tx is None:
            results.append({"opportunity_id": outcome.get("opportunity_id"),
                            "payment_readback": "NOT_MATCHED",
                            "acceptance_attribution": "NOT_ASSESSED"})
            continue
        expected_amount = outcome.get("amount")
        expected_currency = outcome.get("currency")
        checks = {
            "wallet": response.get("miner_id") == wallet == outcome.get("payout_destination"),
            "incoming": tx.get("type") == "transfer_in",
            "confirmed": tx.get("status") == "confirmed",
            "amount": tx.get("amount") == expected_amount,
            "currency": expected_currency == "RTC",
            "received_at": _utc_iso(tx.get("timestamp")) == outcome.get("received_at"),
            "memo": isinstance(outcome.get("payment_record_memo"), str)
                    and tx.get("memo") == outcome.get("payment_record_memo"),
        }
        payment_ok = all(checks.values())
        attribution = capture.get("attribution_checks", {}).get(
            str(outcome.get("opportunity_id", "")).split("#")[-1].split(":")[0], {})
        acceptance = ("PUBLIC_ACCEPTANCE_CHAIN_FOUND"
                      if attribution.get("maintainer_acceptance_comment_found") is True
                      else "PUBLIC_ACCEPTANCE_CHAIN_UNRESOLVED")
        results.append({
            "opportunity_id": outcome.get("opportunity_id"),
            "payment_readback": "MATCHED_CONFIRMED" if payment_ok else "MISMATCH",
            "acceptance_attribution": acceptance,
            "checks": checks,
        })

    return {
        "schema": "value-engine.wallet-receipt-verification/v1",
        "stage": "CAPTURED_PUBLIC_READBACK_VALIDATION",
        "authoritative": False,
        "production_policy_update": False,
        "external_fetch_performed": False,
        "capture_sha256": hashlib.sha256(
            json.dumps(capture, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False).encode("utf-8")
        ).hexdigest(),
        "canonical_response_sha256_recomputed": actual_digest,
        "results": results,
        "summary": {
            "matched_confirmed_payments": sum(
                row["payment_readback"] == "MATCHED_CONFIRMED" for row in results),
            "unresolved_acceptance_attributions": sum(
                row["acceptance_attribution"] == "PUBLIC_ACCEPTANCE_CHAIN_UNRESOLVED"
                for row in results),
            "fiat_cash_total": 0,
            "currency_classification": "RTC crypto-asset; not fiat cash",
        },
        "boundary": (
            "Validates the captured response against historical outcome fields. "
            "Does not authenticate the API operator, prove the capture was not altered "
            "before capture, or authorize policy learning."
        ),
    }
