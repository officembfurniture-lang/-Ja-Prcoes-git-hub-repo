from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Dict

DEBT_KEYS = ("prediction_debt", "contradiction_debt", "redundancy_debt", "claim_debt")
MATERIAL_EFFECT_KINDS = {
    "decision_changed",
    "action_path_opened",
    "action_path_closed",
    "capability_boundary_changed",
}
PROVENANCE_KINDS = {
    "source_document", "artifact_readback", "test_run", "paired_comparison",
}


@dataclass
class Verdict:
    verdict: str
    reason: str
    state_hash: str
    evidence_delta: int
    action_verified: bool
    material_effect_verified: bool
    material_effect_kind: str | None
    burden_delta: float | None
    debt_total: float | None
    next_test: str


def stable_hash(obj: Any) -> str:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_value(value: Any) -> None:
    """Reject coercions and values outside the JSON data model."""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _json_value(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _json_value(item)
        return
    raise ValueError("Non-JSON or non-finite input.")


def _object(value: Any, name: str) -> dict:
    if type(value) is not dict:
        raise ValueError(f"{name} must be an object.")
    return value


def _text(value: Any, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be non-empty text.")
    return value


def _flag(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a boolean.")
    return value


def _number(value: Any, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite non-negative number.")
    try:
        result = float(value)
    except OverflowError:
        raise ValueError(f"{name} is outside the numeric range.") from None
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a finite non-negative number.")
    return result


def _references(value: Any) -> list[str]:
    if type(value) is not list:
        raise ValueError("supporting_evidence_ids must be an array.")
    for identifier in value:
        _text(identifier, "supporting_evidence_id")
    if len(set(value)) != len(value):
        raise ValueError("supporting_evidence_ids must be unique.")
    return value


def _provenance(value: Any) -> bool:
    provenance = _object(value, "provenance")
    kind = _text(provenance.get("kind"), "provenance.kind")
    if kind not in PROVENANCE_KINDS:
        raise ValueError("Unsupported provenance.kind.")
    _text(provenance.get("locator"), "provenance.locator")
    return _flag(provenance.get("readback_verified"), "provenance.readback_verified")


def _validate(record: Any) -> None:
    _json_value(record)
    stable_hash(record)
    _object(record, "record")
    for key in ("previous_state", "candidate_state", "action", "debts", "human_burden", "decision_effect"):
        _object(record.get(key, {}), key)
    for key in ("evidence", "predictions"):
        if type(record.get(key, [])) is not list:
            raise ValueError(f"{key} must be an array.")
    identifiers = set()
    for entry in record.get("evidence", []):
        _object(entry, "evidence entry")
        identifier = _text(entry.get("id"), "evidence.id")
        if identifier in identifiers:
            raise ValueError("Evidence identifiers must be unique.")
        identifiers.add(identifier)
        _text(entry.get("status"), "evidence.status")
        _flag(entry.get("already_known", False), "already_known")
        if "provenance" in entry or entry["status"] == "VERIFIED":
            _provenance(entry.get("provenance"))
    for prediction in record.get("predictions", []):
        _object(prediction, "prediction")
        _text(prediction.get("status"), "prediction.status")
        _references(prediction.get("supporting_evidence_ids", []))
    action = record.get("action", {})
    for key in ("executed", "readback_verified"):
        if key in action:
            _flag(action[key], f"action.{key}")
    if "provenance" in action or action.get("readback_verified") is True:
        _provenance(action.get("provenance"))
    _references(action.get("supporting_evidence_ids", []))
    effect = record.get("decision_effect", {})
    if "verified" in effect:
        _flag(effect["verified"], "decision_effect.verified")
    if "kind" in effect:
        _text(effect["kind"], "decision_effect.kind")
    if "provenance" in effect or effect.get("verified") is True:
        _provenance(effect.get("provenance"))
    _references(effect.get("supporting_evidence_ids", []))
    debts = record.get("debts", {})
    if any(key not in DEBT_KEYS for key in debts):
        raise ValueError("Unknown debt key; debt cannot be silently discarded.")
    values = [_number(debts.get(key, 0), key) for key in DEBT_KEYS]
    _number(sum(values), "debt_total")
    _number(record.get("debt_limit", 3), "debt_limit")
    burden = record.get("human_burden", {})
    if burden:
        _flag(burden.get("measured"), "human_burden.measured")
    for key in ("before", "after"):
        if key in burden or burden.get("measured") is True:
            _number(burden.get(key), f"human_burden.{key}")


def evaluate(record: Dict[str, Any]) -> Verdict:
    """Classify supplied evidence; this pure function does not verify locators."""
    try:
        _validate(record)
    except (ValueError, TypeError, RecursionError, UnicodeError) as error:
        previous = record.get("previous_state", {}) if type(record) is dict else {}
        try:
            _json_value(previous)
            state_hash = stable_hash(_object(previous, "previous_state"))
        except (ValueError, TypeError, RecursionError, UnicodeError):
            state_hash = stable_hash({})
        return Verdict(
            "INPUT_INVALID", str(error), state_hash, 0, False, False, None,
            None, None, "repair_input_without_assuming_missing_values",
        )
    return _evaluate_valid(record)


def _evaluate_valid(record: Dict[str, Any]) -> Verdict:
    previous = record.get("previous_state", {})
    evidence = record.get("evidence", [])
    predictions = record.get("predictions", [])
    action = record.get("action", {})
    debts = record.get("debts", {})
    burden = record.get("human_burden", {})
    decision_effect = record.get("decision_effect", {})

    verified_evidence = [
        e for e in evidence
        if e.get("status") == "VERIFIED" and _provenance(e.get("provenance"))
    ]
    verified_ids = {e["id"] for e in verified_evidence}

    def supported(item: dict) -> bool:
        ids = item.get("supporting_evidence_ids", [])
        return bool(ids) and set(ids).issubset(verified_ids)

    evidence_delta = sum(1 for e in verified_evidence if not e.get("already_known", False))

    action_verified = bool(
        action
        and action.get("executed") is True
        and action.get("readback_verified") is True
        and _provenance(action.get("provenance"))
        and supported(action)
    )

    material_effect_kind = decision_effect.get("kind")
    material_effect_verified = bool(
        decision_effect
        and decision_effect.get("verified") is True
        and _provenance(decision_effect.get("provenance"))
        and material_effect_kind in MATERIAL_EFFECT_KINDS
        and supported(decision_effect)
    )

    debt_total = sum(float(debts.get(k, 0)) for k in DEBT_KEYS)
    burden_measured = burden.get("measured") is True

    burden_delta: float | None
    if burden_measured:
        burden_before = float(burden["before"])
        burden_after = float(burden["after"])
        burden_delta = burden_after - burden_before
    else:
        burden_delta = None

    unsupported_progress = any(
        p.get("status") == "PROGRESS" and not supported(p)
        for p in predictions
    )
    if unsupported_progress:
        return Verdict(
            "DRIVER_REGRESSION",
            "Progress claim without supporting evidence.",
            stable_hash(previous), evidence_delta, action_verified,
            material_effect_verified, material_effect_kind, burden_delta,
            debt_total + 1, "remove_or_support_progress_claim",
        )

    if burden_measured and burden_delta is not None and burden_delta > 0:
        return Verdict(
            "DRIVER_REGRESSION",
            "Human burden increased; a material effect does not waive the regression gate.",
            stable_hash(previous), evidence_delta, action_verified,
            material_effect_verified, material_effect_kind, burden_delta,
            debt_total, "run_control_without_driver",
        )

    if action.get("executed") is True and not action_verified:
        return Verdict(
            "HOLD", "Executed action lacks verified readback or resolved evidence references.",
            stable_hash(previous), evidence_delta, False,
            material_effect_verified, material_effect_kind, burden_delta, debt_total,
            "verify_action_readback_and_evidence_references",
        )

    if evidence_delta == 0 and not action_verified:
        return Verdict(
            "NO_DELTA",
            "No new verified evidence and no verified action.",
            stable_hash(previous), 0, False,
            material_effect_verified, material_effect_kind, burden_delta, debt_total,
            "wait_for_new_evidence_or_run_reversible_test",
        )

    if not material_effect_verified:
        return Verdict(
            "HOLD",
            "Evidence or action is verified, but no independently grounded decision-changing or capability-changing effect is verified.",
            stable_hash(record.get("candidate_state", previous)),
            evidence_delta, action_verified, False, material_effect_kind, burden_delta,
            debt_total, "verify_decision_effect_before_promotion",
        )

    if not burden_measured:
        return Verdict(
            "HOLD",
            "Material effect is verified, but human burden is unmeasured; promotion would convert unknown cost into assumed zero cost.",
            stable_hash(record.get("candidate_state", previous)),
            evidence_delta, action_verified, True, material_effect_kind, None, debt_total,
            "measure_human_burden_before_promotion",
        )

    if debt_total > float(record.get("debt_limit", 3)):
        return Verdict(
            "HOLD",
            "Material effect exists but unresolved debt exceeds threshold.",
            stable_hash(record.get("candidate_state", previous)),
            evidence_delta, action_verified, True, material_effect_kind, burden_delta,
            debt_total, "pay_highest_debt_before_new_exploration",
        )

    return Verdict(
        "PROMOTE",
        "Verified material effect exists without threshold-breaking debt or burden regression.",
        stable_hash(record.get("candidate_state", previous)),
        evidence_delta, action_verified, True, material_effect_kind, burden_delta,
        debt_total, "freeze_new_baseline_and_register_one_falsifiable_prediction",
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
