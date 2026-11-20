"""Shadow-only ranking experiment using explicitly untrusted outcome claims.

This module does NOT authenticate verifier identities, verify external evidence,
or mutate policy.json. A caller-supplied attestation is only a claim. This module
can test the shape and possible decision impact of such claims; it cannot turn
them into trusted receipts or authorize a production policy update.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime
from typing import Any

SCHEMA = "value-engine.policy-feedback/v2"
HEX_256 = re.compile(r"^[0-9a-f]{64}$")


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None and parsed.utcoffset() is not None
    except (TypeError, ValueError):
        return False


def _valid_outcome_claim(row: Any) -> tuple[bool, str]:
    if not isinstance(row, dict):
        return False, "CLAIM_NOT_OBJECT"
    required = ("receipt_id", "settlement_status", "source_family",
                "opportunity_class", "amount", "currency", "received_at",
                "verification")
    if any(key not in row for key in required):
        return False, "REQUIRED_FIELD_MISSING"
    if row["settlement_status"] != "PAID":
        return False, "NOT_CLAIMED_PAID"
    if (not isinstance(row["amount"], (int, float))
            or isinstance(row["amount"], bool)
            or (isinstance(row["amount"], float) and not math.isfinite(row["amount"]))
            or row["amount"] <= 0):
        return False, "INVALID_AMOUNT"
    if not all(_nonempty_string(row[k]) for k in (
            "receipt_id", "source_family", "opportunity_class", "currency",
            "received_at")):
        return False, "INVALID_IDENTITY_FIELD"
    if not _valid_timestamp(row["received_at"]):
        return False, "INVALID_RECEIVED_AT"
    claim = row["verification"]
    if not isinstance(claim, dict):
        return False, "VERIFICATION_CLAIM_MISSING"
    if claim.get("status") != "INDEPENDENTLY_VERIFIED":
        return False, "NO_INDEPENDENT_VERIFICATION_CLAIM"
    if not all(_nonempty_string(claim.get(k)) for k in (
            "verifier", "method", "evidence_uri", "verified_at",
            "verification_record_uri")):
        return False, "VERIFICATION_CLAIM_INCOMPLETE"
    if not _valid_timestamp(claim["verified_at"]):
        return False, "INVALID_VERIFIED_AT"
    for key in ("evidence_sha256", "verification_record_sha256"):
        digest = claim.get(key)
        if not isinstance(digest, str) or not HEX_256.fullmatch(digest):
            return False, "INVALID_" + key.upper()
    # Deliberately no trust decision here: all fields above are caller supplied.
    return True, "STRUCTURALLY_VALID_UNTRUSTED_CLAIM"


def _validate_candidates(candidates: Any) -> tuple[bool, str]:
    if not isinstance(candidates, list) or not candidates:
        return False, "CANDIDATES_MUST_BE_NONEMPTY_LIST"
    seen: set[str] = set()
    for row in candidates:
        if not isinstance(row, dict):
            return False, "CANDIDATE_NOT_OBJECT"
        candidate_id = row.get("candidate_id")
        if not _nonempty_string(candidate_id):
            return False, "CANDIDATE_ID_MISSING"
        if candidate_id in seen:
            return False, "DUPLICATE_CANDIDATE_ID"
        seen.add(candidate_id)
        if not _nonempty_string(row.get("source_family")):
            return False, "CANDIDATE_SOURCE_FAMILY_MISSING"
        rank = row.get("base_rank")
        if not isinstance(rank, int) or isinstance(rank, bool):
            return False, "CANDIDATE_BASE_RANK_INVALID"
    return True, "CANDIDATES_VALID"


def build_shadow_feedback(outcome_claims: list[dict[str, Any]],
                          candidates: list[dict[str, Any]],
                          input_revision: str) -> dict[str, Any]:
    """Compare baseline and claim-conditioned rankings without authority."""
    if not _nonempty_string(input_revision):
        raise ValueError("input_revision is required")
    if not isinstance(outcome_claims, list):
        raise ValueError("outcome_claims must be a list")
    valid_candidates, candidate_reason = _validate_candidates(candidates)
    if not valid_candidates:
        raise ValueError(candidate_reason)
    try:
        digest_input = json.dumps(
            {"input_revision": input_revision, "outcome_claims": outcome_claims,
             "candidates": candidates},
            sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    except (TypeError, ValueError) as exc:
        raise ValueError("inputs must be finite JSON-compatible data") from exc

    claim_id_counts = Counter(
        row.get("receipt_id") for row in outcome_claims
        if isinstance(row, dict) and isinstance(row.get("receipt_id"), str)
    )
    eligible_claims: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in outcome_claims:
        ok, reason = _valid_outcome_claim(row)
        claim_id = row.get("receipt_id", "<unknown>") if isinstance(row, dict) else "<unknown>"
        if not ok:
            rejected.append({"receipt_id": str(claim_id), "reason": reason})
            continue
        if claim_id_counts[claim_id] > 1:
            rejected.append({"receipt_id": claim_id, "reason": "DUPLICATE_CLAIM_ID"})
            continue
        seen.add(claim_id)
        eligible_claims.append(row)

    counts = Counter(row["source_family"] for row in eligible_claims)
    preference = sorted(counts, key=lambda family: (-counts[family], family))
    preference_rank = {family: index for index, family in enumerate(preference)}
    baseline = sorted(candidates, key=lambda row: (
        row["base_rank"], row["candidate_id"]))
    shadow = sorted(candidates, key=lambda row: (
        row["base_rank"],
        preference_rank.get(row["source_family"], len(preference_rank)),
        row["candidate_id"]))
    baseline_ids = [row["candidate_id"] for row in baseline]
    shadow_ids = [row["candidate_id"] for row in shadow]
    return {
        "schema": SCHEMA,
        "mode": "SHADOW_ONLY",
        "authoritative": False,
        "policy_mutated": False,
        "external_action_taken": False,
        "caller_supplied_claims_are_authenticated": False,
        "input_revision": input_revision,
        "input_sha256": hashlib.sha256(digest_input).hexdigest(),
        "eligible_untrusted_claim_ids": sorted(seen),
        "rejected_claims": rejected,
        "source_family_claim_counts": dict(sorted(counts.items())),
        "baseline_order": baseline_ids,
        "shadow_order": shadow_ids,
        "decision_changed": baseline_ids != shadow_ids,
        "proposed_source_family_preference": preference,
        "evidence_boundary": (
            "The module validates claim structure only. It does not authenticate "
            "the verifier, validate evidence URIs or hashes against external systems, "
            "or establish that payment occurred. Synthetic/caller-supplied claims "
            "may change this shadow ranking; they cannot authorize production policy."
        ),
    }
