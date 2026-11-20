"""Shadow-only, provenance-gated outcome feedback for source selection.

This module validates receipt structure, not external evidence. It never mutates
policy.json or grants authority; a trusted upstream verifier remains mandatory.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime
from typing import Any

SCHEMA = "value-engine.policy-feedback/v1"
HEX_256 = re.compile(r"^[0-9a-f]{64}$")


def _valid_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None and parsed.utcoffset() is not None
    except (TypeError, ValueError):
        return False


def _valid_receipt(row: Any) -> tuple[bool, str]:
    if not isinstance(row, dict):
        return False, "RECEIPT_NOT_OBJECT"
    required = ("receipt_id", "settlement_status", "source_family",
                "opportunity_class", "amount", "currency", "received_at",
                "verification")
    if any(key not in row for key in required):
        return False, "REQUIRED_FIELD_MISSING"
    if row["settlement_status"] != "PAID":
        return False, "NOT_PAID"
    amount = row["amount"]
    if (not isinstance(amount, (int, float)) or isinstance(amount, bool)
            or not math.isfinite(amount) or amount <= 0):
        return False, "INVALID_AMOUNT"
    if not all(isinstance(row[k], str) and row[k].strip()
               for k in ("receipt_id", "source_family", "opportunity_class", "currency")):
        return False, "INVALID_IDENTITY_FIELD"
    if not isinstance(row["received_at"], str) or not _valid_timestamp(row["received_at"]):
        return False, "INVALID_RECEIVED_AT"
    attestation = row["verification"]
    if not isinstance(attestation, dict):
        return False, "VERIFICATION_ATTESTATION_MISSING"
    if attestation.get("status") != "INDEPENDENTLY_VERIFIED":
        return False, "NOT_INDEPENDENTLY_VERIFIED"
    if not all(isinstance(attestation.get(k), str) and attestation[k].strip()
               for k in ("verifier", "method", "evidence_uri",
                         "verified_at", "verification_record_uri")):
        return False, "VERIFICATION_PROVENANCE_INCOMPLETE"
    if not _valid_timestamp(attestation["verified_at"]):
        return False, "INVALID_VERIFIED_AT"
    digest = attestation.get("evidence_sha256")
    record_digest = attestation.get("verification_record_sha256")
    if not isinstance(digest, str) or not HEX_256.fullmatch(digest):
        return False, "EVIDENCE_HASH_INVALID"
    if not isinstance(record_digest, str) or not HEX_256.fullmatch(record_digest):
        return False, "VERIFICATION_RECORD_HASH_INVALID"
    return True, "ACCEPTED_FOR_SHADOW_EVALUATION"


def _validate_candidates(candidates: Any) -> None:
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")
    seen_ids: set[str] = set()
    for row in candidates:
        if not isinstance(row, dict):
            raise ValueError("every candidate must be an object")
        candidate_id = row.get("candidate_id")
        family = row.get("source_family")
        base_rank = row.get("base_rank")
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise ValueError("every candidate requires a non-empty candidate_id")
        if candidate_id in seen_ids:
            raise ValueError("candidate_id values must be unique")
        seen_ids.add(candidate_id)
        if not isinstance(family, str) or not family.strip():
            raise ValueError("every candidate requires a non-empty source_family")
        if not isinstance(base_rank, int) or isinstance(base_rank, bool):
            raise ValueError("every candidate requires integer base_rank")


def build_shadow_feedback(receipts: list[dict[str, Any]],
                          candidates: list[dict[str, Any]],
                          input_revision: str) -> dict[str, Any]:
    """Build a deterministic replayable ranking without live policy mutation."""
    if not isinstance(input_revision, str) or not input_revision.strip():
        raise ValueError("input_revision is required")
    if not isinstance(receipts, list):
        raise ValueError("receipts must be a list")
    _validate_candidates(candidates)

    # Reject non-JSON and non-finite inputs rather than producing an unstable digest.
    try:
        digest_input = json.dumps(
            {"input_revision": input_revision, "receipts": receipts,
             "candidates": candidates},
            sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    except (TypeError, ValueError) as exc:
        raise ValueError("inputs must be finite, JSON-serializable values") from exc

    id_counts = Counter(
        row.get("receipt_id") for row in receipts
        if isinstance(row, dict) and isinstance(row.get("receipt_id"), str)
    )
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in receipts:
        ok, reason = _valid_receipt(row)
        receipt_id = row.get("receipt_id", "<unknown>") if isinstance(row, dict) else "<unknown>"
        if not ok:
            rejected.append({"receipt_id": str(receipt_id), "reason": reason})
            continue
        if id_counts[receipt_id] > 1:
            rejected.append({"receipt_id": receipt_id, "reason": "DUPLICATE_RECEIPT"})
            continue
        seen.add(receipt_id)
        accepted.append(row)

    counts = Counter(row["source_family"] for row in accepted)
    preferred = sorted(counts, key=lambda key: (-counts[key], key))
    preference_rank = {name: index for index, name in enumerate(preferred)}

    def rank(row: dict[str, Any], use_feedback: bool) -> tuple[Any, ...]:
        feedback_rank = preference_rank.get(row["source_family"], len(preference_rank)) if use_feedback else 0
        return (row["base_rank"], feedback_rank, row["candidate_id"])

    baseline = sorted(candidates, key=lambda row: rank(row, False))
    shadow = sorted(candidates, key=lambda row: rank(row, True))
    baseline_ids = [row["candidate_id"] for row in baseline]
    shadow_ids = [row["candidate_id"] for row in shadow]
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
