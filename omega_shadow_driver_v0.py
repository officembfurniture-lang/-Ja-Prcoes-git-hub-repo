from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Dict

DEBT_KEYS = ("prediction_debt", "contradiction_debt", "redundancy_debt", "claim_debt")


@dataclass
class Verdict:
    verdict: str
    reason: str
    state_hash: str
    evidence_delta: int
    action_verified: bool
    burden_delta: float | None
    debt_total: float
    next_test: str


def stable_hash(obj: Any) -> str:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def evaluate(record: Dict[str, Any]) -> Verdict:
    previous = record.get("previous_state", {})
    evidence = record.get("evidence", [])
    predictions = record.get("predictions", [])
    action = record.get("action", {})
    debts = record.get("debts", {})
    burden = record.get("human_burden", {})

    verified_evidence = [
        e for e in evidence
        if e.get("status") == "VERIFIED" and e.get("provenance")
    ]
    evidence_delta = sum(1 for e in verified_evidence if not e.get("already_known", False))

    action_verified = bool(
        action
        and action.get("executed") is True
        and action.get("readback_verified") is True
        and action.get("provenance")
    )

    debt_total = sum(float(debts.get(k, 0) or 0) for k in DEBT_KEYS)

    explicit_measurement_flag = burden.get("measured")
    if explicit_measurement_flag is False:
        burden_measured = False
    elif explicit_measurement_flag is True:
        burden_measured = "before" in burden and "after" in burden
    else:
        burden_measured = "before" in burden and "after" in burden

    burden_delta: float | None
    if burden_measured:
        burden_before = float(burden["before"] or 0)
        burden_after = float(burden["after"] or 0)
        burden_delta = burden_after - burden_before
    else:
        burden_delta = None

    unsupported_progress = any(
        p.get("status") == "PROGRESS" and not p.get("supporting_evidence_ids")
        for p in predictions
    )
    if unsupported_progress:
        return Verdict(
            "DRIVER_REGRESSION",
            "Progress claim without supporting evidence.",
            stable_hash(previous), evidence_delta, action_verified, burden_delta,
            debt_total + 1, "remove_or_support_progress_claim",
        )

    if burden_measured and burden_delta is not None and burden_delta > 0 and evidence_delta == 0 and not action_verified:
        return Verdict(
            "DRIVER_REGRESSION",
            "Human burden increased without verified information or action gain.",
            stable_hash(previous), evidence_delta, action_verified, burden_delta,
            debt_total, "run_control_without_driver",
        )

    if evidence_delta == 0 and not action_verified:
        return Verdict(
            "NO_DELTA",
            "No new verified evidence and no verified action.",
            stable_hash(previous), 0, False, burden_delta, debt_total,
            "wait_for_new_evidence_or_run_reversible_test",
        )

    if not burden_measured:
        return Verdict(
            "HOLD",
            "Verified delta exists, but human burden is unmeasured; promotion would convert unknown cost into assumed zero cost.",
            stable_hash(record.get("candidate_state", previous)),
            evidence_delta, action_verified, None, debt_total,
            "measure_human_burden_before_promotion",
        )

    if debt_total > float(record.get("debt_limit", 3)):
        return Verdict(
            "HOLD",
            "Delta exists but unresolved debt exceeds threshold.",
            stable_hash(record.get("candidate_state", previous)),
            evidence_delta, action_verified, burden_delta, debt_total,
            "pay_highest_debt_before_new_exploration",
        )

    return Verdict(
        "PROMOTE",
        "Verified delta exists without threshold-breaking debt or burden regression.",
        stable_hash(record.get("candidate_state", previous)),
        evidence_delta, action_verified, burden_delta, debt_total,
        "freeze_new_baseline_and_register_one_falsifiable_prediction",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic shadow controller for JA-process cycle outputs.")
    parser.add_argument("record", help="Path to a cycle record JSON file")
    args = parser.parse_args()
    with open(args.record, "r", encoding="utf-8") as f:
        record = json.load(f)
    print(json.dumps(asdict(evaluate(record)), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
