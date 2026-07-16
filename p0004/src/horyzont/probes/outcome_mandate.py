from __future__ import annotations

import argparse
import hashlib
import json
import operator
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse


SCHEMA = "horyzont.outcome-mandate/v0.1"
ALLOWED_AUTHORITIES = {"A0", "A1", "A2", "A3"}
OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise ValueError("timestamps must be ISO-8601") from error


def validate_draft(draft: dict[str, Any]) -> None:
    required_text = ("issuer", "task", "kill_gate", "expires_at")
    for key in required_text:
        if not str(draft.get(key, "")).strip():
            raise ValueError(f"mandate field {key} cannot be empty")
    _parse_time(draft["expires_at"])
    if draft.get("authority") not in ALLOWED_AUTHORITIES:
        raise ValueError("authority must be A0, A1, A2 or A3")
    budget = draft.get("budget")
    if not isinstance(budget, dict) or float(budget.get("amount", -1)) < 0 or not budget.get("currency"):
        raise ValueError("budget requires a non-negative amount and currency")
    criteria = draft.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("at least one outcome criterion is required")
    metric_names = set()
    for criterion in criteria:
        metric = str(criterion.get("metric", "")).strip()
        if not metric or metric in metric_names:
            raise ValueError("criterion metric names must be non-empty and unique")
        metric_names.add(metric)
        if criterion.get("operator") not in OPERATORS:
            raise ValueError(f"unsupported operator for criterion {metric}")
        if "target" not in criterion:
            raise ValueError(f"criterion {metric} requires a target")
    allowed_sources = draft.get("evidence_policy", {}).get("allowed_schemes", [])
    if not allowed_sources or any(value not in {"https", "dataset", "metric", "transaction"} for value in allowed_sources):
        raise ValueError("evidence_policy.allowed_schemes must declare supported external provenance schemes")


def freeze_mandate(draft: dict[str, Any]) -> dict[str, Any]:
    validate_draft(draft)
    body = {
        "schema": SCHEMA,
        "issuer": draft["issuer"],
        "task": draft["task"],
        "authority": draft["authority"],
        "budget": draft["budget"],
        "criteria": draft["criteria"],
        "evidence_policy": draft["evidence_policy"],
        "kill_gate": draft["kill_gate"],
        "expires_at": draft["expires_at"],
        "metadata": draft.get("metadata", {}),
        "truth_boundary": {
            "content_hash_is_signature": False,
            "payment_authorized": False,
            "statement": "The hash freezes local content. Identity signatures and payment authority require external verified credentials and separately active A3 policy.",
        },
    }
    body["mandate_hash"] = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    return body


def evaluate_attestation(mandate: dict[str, Any], attestation: dict[str, Any]) -> dict[str, Any]:
    mandate_hash = mandate.get("mandate_hash")
    body = {key: value for key, value in mandate.items() if key != "mandate_hash"}
    expected_hash = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    integrity_valid = bool(mandate_hash) and mandate_hash == expected_hash
    observed_at = _parse_time(attestation["observed_at"])
    expires_at = _parse_time(mandate["expires_at"])
    unexpired = observed_at <= expires_at
    hash_matches = attestation.get("mandate_hash") == mandate_hash
    metrics = attestation.get("metrics", {})

    evaluations = []
    for criterion in mandate["criteria"]:
        metric = criterion["metric"]
        actual_present = metric in metrics
        actual = metrics.get(metric)
        try:
            passed = actual_present and OPERATORS[criterion["operator"]](actual, criterion["target"])
        except TypeError:
            passed = False
        evaluations.append(
            {
                "metric": metric,
                "operator": criterion["operator"],
                "target": criterion["target"],
                "actual": actual,
                "passed": bool(passed),
            }
        )

    allowed_schemes = set(mandate["evidence_policy"]["allowed_schemes"])
    evidence_refs = attestation.get("evidence_refs", [])
    evidence_valid = bool(evidence_refs) and all(urlparse(value).scheme in allowed_schemes for value in evidence_refs)
    accepted = all(
        [
            integrity_valid,
            unexpired,
            hash_matches,
            evidence_valid,
            all(item["passed"] for item in evaluations),
        ]
    )
    return {
        "schema": "horyzont.outcome-verdict/v0.1",
        "mandate_hash": mandate_hash,
        "accepted": accepted,
        "checks": {
            "mandate_integrity_valid": integrity_valid,
            "attestation_bound_to_mandate": hash_matches,
            "attestation_before_expiry": unexpired,
            "external_evidence_references_valid": evidence_valid,
            "all_criteria_passed": all(item["passed"] for item in evaluations),
        },
        "criteria": evaluations,
        "truth_boundary": {
            "evidence_semantics_independently_verified": False,
            "payment_released": False,
            "statement": "The verifier checks declared structure, references and decision rules; it does not independently establish that an evidence source is truthful.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze or verify an Outcome Mandate")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("draft")
    create.add_argument("--output")
    verify = sub.add_parser("verify")
    verify.add_argument("mandate")
    verify.add_argument("attestation")
    verify.add_argument("--output")
    args = parser.parse_args()

    if args.command == "create":
        result = freeze_mandate(json.loads(Path(args.draft).read_text(encoding="utf-8")))
    else:
        mandate = json.loads(Path(args.mandate).read_text(encoding="utf-8"))
        attestation = json.loads(Path(args.attestation).read_text(encoding="utf-8"))
        result = evaluate_attestation(mandate, attestation)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
