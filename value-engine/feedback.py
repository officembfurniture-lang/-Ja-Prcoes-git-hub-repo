"""Deterministic, read-only next-step selector for the VALUE_ENGINE feedback loop.

It does not execute work, authorize spending, or change repository state.
"""
from __future__ import annotations

import json
from pathlib import Path

from health_report import build


def recommend(report: dict) -> dict:
    alerts = set(report.get("diagnostic_alerts", []))
    if "unsettled_acceptances" in alerts:
        focus = "VERIFY_SETTLEMENT"
        reason = "Accepted work exists without a verified final payment."
        next_action = "Inspect primary settlement evidence; do not infer payment."
    elif "no_verified_conversion" in alerts:
        focus = "REVIEW_SOURCE_QUALITY"
        reason = "Observations exist but none is recorded as verified."
        next_action = "Audit a bounded sample against original primary sources."
    elif report.get("verified", 0) > report.get("delivered", 0):
        focus = "REVIEW_DELIVERY_ROUTES"
        reason = "Verified opportunities exceed recorded deliveries."
        next_action = "Check available authorized delivery routes and acceptance criteria."
    else:
        focus = "MAINTAIN_AND_MEASURE"
        reason = "No higher-priority funnel gap identified from internal counters."
        next_action = "Continue sensing and require independent evidence for outcomes."
    return {
        "schema_version": 1,
        "mode": "ADVISORY_ONLY",
        "focus": focus,
        "reason": reason,
        "next_action": next_action,
        "authorization_granted": False,
        "external_action_taken": False,
        "evidence_boundary": "Internal counters and alerts only; independently verify before action.",
    }


def main() -> None:
    print(json.dumps(recommend(build()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
