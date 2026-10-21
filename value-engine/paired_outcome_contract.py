"""Strict input-contract check for paired outcomes; never promotes Omega.

This checks report completeness and conservative disposition only. It does not
fetch locators, authenticate an evaluator, or establish real-world truth.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SHA256 = re.compile(r"^[0-9a-f]{64}$")


def assess(report: object) -> dict:
    if type(report) is not dict or report.get("schema") != "paired-outcome-report/v1":
        return {"status": "HOLD", "reason": "invalid_report_schema", "promotion": False}
    pairs = report.get("pairs")
    if type(pairs) is not list or not pairs:
        return {"status": "HOLD", "reason": "no_pairs", "promotion": False}

    changed_and_supported = 0
    for index, pair in enumerate(pairs):
        if type(pair) is not dict:
            return {"status": "HOLD", "reason": f"pair_{index}_not_object", "promotion": False}
        input_hash = pair.get("frozen_input_sha256")
        if type(input_hash) is not str or not SHA256.fullmatch(input_hash):
            return {"status": "HOLD", "reason": f"pair_{index}_input_not_frozen", "promotion": False}
        baseline = pair.get("baseline")
        candidate = pair.get("candidate")
        outcome = pair.get("independent_outcome")
        burden = pair.get("correction_burden")
        if any(type(x) is not dict for x in (baseline, candidate, outcome, burden)):
            return {"status": "HOLD", "reason": f"pair_{index}_missing_sections", "promotion": False}
        if any(type(x.get("decision")) is not str or not x["decision"].strip()
               for x in (baseline, candidate)):
            return {"status": "HOLD", "reason": f"pair_{index}_decision_missing", "promotion": False}
        if outcome.get("verified") is not True:
            return {"status": "HOLD", "reason": f"pair_{index}_outcome_unverified", "promotion": False}
        locator = outcome.get("evidence_url")
        if type(locator) is not str or not locator.startswith("https://"):
            return {"status": "HOLD", "reason": f"pair_{index}_outcome_locator_invalid", "promotion": False}
        verifier = outcome.get("verified_by")
        operator = report.get("candidate_operator")
        if (type(verifier) is not str or not verifier.strip()
                or type(operator) is not str or not operator.strip()
                or verifier.strip().casefold() == operator.strip().casefold()):
            return {"status": "HOLD", "reason": f"pair_{index}_independence_not_established", "promotion": False}
        if outcome.get("candidate_better_than_baseline") not in (True, False) or type(outcome.get("candidate_better_than_baseline")) is not bool:
            return {"status": "HOLD", "reason": f"pair_{index}_comparison_missing", "promotion": False}
        if burden.get("measured") is not True:
            return {"status": "HOLD", "reason": f"pair_{index}_burden_unmeasured", "promotion": False}
        before, after = burden.get("baseline"), burden.get("candidate")
        if (type(before) is not int or before < 0
                or type(after) is not int or after < 0):
            return {"status": "HOLD", "reason": f"pair_{index}_burden_invalid", "promotion": False}
        if after > before:
            return {"status": "DRIVER_REGRESSION", "reason": f"pair_{index}_correction_burden_increased", "promotion": False}
        if baseline["decision"] != candidate["decision"] and outcome["candidate_better_than_baseline"]:
            changed_and_supported += 1

    if changed_and_supported:
        return {
            "status": "READY_FOR_EXTERNAL_ADJUDICATION",
            "reason": "complete paired claims are present; external evidence and independence still require manual verification",
            "decision_changing_pairs": changed_and_supported,
            "promotion": False,
        }
    return {
        "status": "HOLD",
        "reason": "no independently claimed decision-changing benefit with non-increased measured burden",
        "decision_changing_pairs": 0,
        "promotion": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    result = assess(json.loads(args.report.read_text(encoding="utf-8")))
    print(json.dumps(result, sort_keys=True))
    if result["status"] in ("HOLD", "DRIVER_REGRESSION"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
