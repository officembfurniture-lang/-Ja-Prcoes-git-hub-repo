"""Shadow-only, provenance-gated outcome feedback for source selection.

This module does not verify external evidence itself and never mutates policy.json.
It accepts only upstream receipts that have already passed independent verification,
then validates their structure and emits a deterministic candidate ranking.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any

SCHEMA = "value-engine.policy-feedback/v1"
HEX_256 = re.compile(r"^[0-9a-f]{64}$")


def _valid_receipt(row: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(row, dict):
        return False, "RECEIPT_NOT_OBJECT"
    required = ("receipt_id", "settlement_status", "source_family",
                "opportunity_class", "amount", "currency", "received_at",
                "verification")
    if any(key not in row for key in required):
        return False, "REQUIRED_FIELD_MISSING"
    if row["settlement_status"] != "PAID":
        return False, "NOT_PAID"
    if not isinstance(row["amount"], (int, float)) or isinstance(row["amount"], bool) or row["amount"] <= 0:
        return False, "INVALID_AMOUNT"
    if not all(isinstance(row[k], str) and row[k].strip()
               for k in ("receipt_id", "source_family", "opportunity_class",
                         "currency", "received_at")):
        return False, "INVALID_IDENTITY_FIELD"
    attestation = row["verification"]
    if not isinstance(attestation, dict):
        return False, "VERIFICATION_ATTESTATION_MISSING"
    if attestation.get("status") != "INDEPENDENTLY_VERIFIED":
        return False, "NOT_INDEPENDENTLY_VERIFIED"
    if not all(isinstance(attestation.get(k), str) and attestation[k].strip()
                for k in ("verifier", "method", "evidence_uri",
                          "verified_at", "verification_record_uri")):
        return False, "VERIFICATION_PROVENANCE_INCOMPLETE"
    digest = attestation.get("evidence_sha256")
    record_digest = attestation.get("verification_record_sha256")
    if not isinstance(digest, str) or not HEX_256.fullmatch(digest):
        return False, "EVIDENCE_HASH_INVALID"
    if not isinstance(record_digest, str) or not HEX_256.fullmatch(record_digest):
        return False, "VERIFICATION_RECORD_HASH_INVALID"
    return True, "ACCEPTED_FOR_SHADOW_EVALUATION"


def build_shadow_feedback(receipts: list[dict[str, Any]],
                          candidates: list[dict[str, Any]],
                          input_revision: str) -> dict[str, Any]:
    """Build a replayable candidate ranking; no live policy or external action."""
    if not isinstance(input_revision, str) or not input_revision.strip():
        raise ValueError("input_revision is required")
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in receipts:
        ok, reason = _valid_receipt(row)
        receipt_id = row.get("receipt_id", "<unknown>") if isinstance(row, dict) else "<unknown>"
        if not ok:
            rejected.append({"receipt_id": str(receipt_id), "reason": reason})
            continue
        if receipt_id in seen:
            rejected.append({"receipt_id": receipt_id, "reason": "DUPLICATE_RECEIPT"})
            continue
        seen.add(receipt_id)
        accepted.append(row)

    counts = Counter(row["source_family"] for row in accepted)
    preferred = sorted(counts, key=lambda key: (-counts[key], key))
    preference_rank = {name: index for index, name in enumerate(preferred)}

    def rank(row: dict[str, Any], use_feedback: bool) -> tuple[Any, ...]:
        base_rank = row.get("base_rank")
        if not isinstance(base_rank, int) or isinstance(base_rank, bool):
            raise ValueError("every candidate requires integer base_rank")
        family = row.get("source_family")
        feedback_rank = preference_rank.get(family, len(preference_rank)) if use_feedback else 0
        return (feedback_rank, base_rank, str(row.get("candidate_id", "")))

    baseline = sorted(candidates, key=lambda row: (row["base_rank"], str(row.get("candidate_id", ""))))
    shadow = sorted(candidates, key=lambda row: rank(row, True))
    baseline_ids = [row.get("candidate_id") for row in baseline]
    shadow_ids = [row.get("candidate_id") for row in shadow]
    accepted_material = [
        {"receipt_id": row["receipt_id"], "source_family": row["source_family"],
         "opportunity_class": row["opportunity_class"], "amount": row["amount"],
         "currency": row["currency"], "received_at": row["received_at"],
         "verification": row["verification"]}
        for row in accepted
    ]
    digest_input = json.dumps(
        {"input_revision": input_revision, "receipts": accepted_material,
         "candidates": candidates}, sort_keys=True, separators=(",", ":")
    ).encode()
    return {
        "schema": SCHEMA,
        "mode": "SHADOW_ONLY",
        "authoritative": False,
        "policy_mutated": False,
        "external_action_taken": False,
        "input_revision": input_revision,
        "input_sha256": hashlib.sha256(digest_input).hexdigest(),
        "accepted_receipt_ids": sorted(seen),
        "rejected_receipts": rejected,
        "source_family_counts": dict(sorted(counts.items())),
        "baseline_order": baseline_ids,
        "shadow_order": shadow_ids,
        "decision_changed": baseline_ids != shadow_ids,
        "proposed_source_family_preference": preferred,
        "evidence_boundary": (
            "Structural validation only: upstream independent verification is a prerequisite, "
            "not performed by this module. This output is a shadow ranking, not proof of "
            "causal benefit and not an update to policy.json."
        ),
    }
