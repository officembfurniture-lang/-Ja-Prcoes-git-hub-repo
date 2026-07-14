from __future__ import annotations

import argparse
import hashlib
import json
import operator
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse


SCHEMA = "horyzont.measurement-protocol/v0.1"
OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}
VARIABLE_ROLES = {"independent", "dependent", "control", "context"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_draft(draft: dict[str, Any]) -> None:
    for field in ("id", "question", "hypothesis", "expires_at"):
        if not str(draft.get(field, "")).strip():
            raise ValueError(f"measurement field {field} cannot be empty")
    try:
        expiry = datetime.fromisoformat(draft["expires_at"].replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise ValueError("expires_at must be ISO-8601") from error
    if expiry.tzinfo is None:
        raise ValueError("expires_at must include a timezone")
    if draft.get("authority") != "A1":
        raise ValueError("the compiler accepts only bounded A1 protocols")

    anomaly = draft.get("anomaly", {})
    if not str(anomaly.get("metric", "")).strip() or "observed" not in anomaly:
        raise ValueError("anomaly requires a metric and observed value")

    variables = draft.get("variables")
    if not isinstance(variables, list) or len(variables) < 2:
        raise ValueError("at least two declared variables are required")
    names: set[str] = set()
    for variable in variables:
        name = str(variable.get("name", "")).strip()
        if not name or name in names:
            raise ValueError("variable names must be non-empty and unique")
        names.add(name)
        if variable.get("role") not in VARIABLE_ROLES:
            raise ValueError(f"unsupported variable role for {name}")
    if not any(variable["role"] == "dependent" for variable in variables):
        raise ValueError("a dependent variable is required")

    measurement = draft.get("measurement", {})
    source_ref = str(measurement.get("source_ref", ""))
    if urlparse(source_ref).scheme not in {"https", "dataset", "metric", "artifact"}:
        raise ValueError("measurement source_ref must use an auditable scheme")
    if int(measurement.get("sample_count", 0)) < 2:
        raise ValueError("measurement sample_count must be at least two")

    decision = draft.get("decision_rule", {})
    if decision.get("operator") not in OPERATORS or "threshold" not in decision:
        raise ValueError("decision_rule requires a supported operator and threshold")
    if decision.get("metric") not in names:
        raise ValueError("decision_rule metric must name a declared variable")


def compile_protocol(draft: dict[str, Any]) -> dict[str, Any]:
    validate_draft(draft)
    hazard = draft.get("hazard", {})
    review_reasons = [
        label
        for label, active in {
            "human participation": bool(hazard.get("involves_people")),
            "living systems": bool(hazard.get("involves_living_systems")),
            "hazardous materials": bool(hazard.get("involves_hazardous_materials")),
            "critical infrastructure": bool(hazard.get("involves_critical_infrastructure")),
        }.items()
        if active
    ]
    protocol: dict[str, Any] = {
        "schema": SCHEMA,
        "id": draft["id"],
        "question": draft["question"],
        "hypothesis": draft["hypothesis"],
        "anomaly": draft["anomaly"],
        "variables": draft["variables"],
        "measurement": draft["measurement"],
        "decision_rule": draft["decision_rule"],
        "counterfactual": draft.get("counterfactual", "No intervention or comparison baseline."),
        "authority": "A1",
        "expires_at": draft["expires_at"],
        "review": {
            "required_before_execution": bool(review_reasons),
            "reasons": review_reasons,
        },
        "truth_boundary": {
            "experiment_executed": False,
            "result_observed": False,
            "causal_effect_established": False,
            "statement": (
                "This artifact freezes a measurement design. It does not execute the "
                "experiment or establish the hypothesis."
            ),
        },
    }
    protocol["protocol_hash"] = hashlib.sha256(
        canonical_json(protocol).encode("utf-8")
    ).hexdigest()
    return protocol


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile an anomaly into a frozen A1 measurement protocol")
    parser.add_argument("input", help="Measurement draft JSON")
    parser.add_argument("--output", help="Optional result JSON path")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rendered = json.dumps(compile_protocol(payload), ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
