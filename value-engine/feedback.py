"""Deterministic, read-only next-step selector for the VALUE_ENGINE feedback loop.

The primary focus stays singular; parallel diagnostics are preserved so a
second active failure is not hidden by first-priority selection.
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

    secondary_diagnostics = []
    if "zero_direct_readback_captures" in alerts:
        attempts = int(report.get("last_sensor_direct_readback_attempts", 0) or 0)
        captures = int(report.get("last_sensor_direct_readback_captures", 0) or 0)
        http_404s = int(report.get("last_sensor_direct_readback_http_404s", 0) or 0)
        if attempts > 0 and captures == 0:
            all_404 = http_404s >= attempts
            secondary_diagnostics.append({
                "code": "DIRECT_READBACK_ZERO_CAPTURE_ALL_404" if all_404 else "DIRECT_READBACK_ZERO_CAPTURE",
                "priority": "SECONDARY",
                "status": "OPEN",
                "observed": {
                    "attempts": attempts,
                    "captures": captures,
                    "http_404s": http_404s,
                },
                "next_action": (
                    "Respect the existing cooldown for failed URLs. On the next sensor cycle, "
                    "inspect one freshly surfaced primary-source candidate and record the exact "
                    "readback result; do not retry the same failed URL merely to fill the quota."
                ),
                "evidence_boundary": (
                    "HTTP 404 establishes that this read path did not resolve the target; it does "
                    "not by itself prove deletion, a global source outage, or any payment status."
                ),
            })

    return {
        "schema_version": 1,
        "mode": "ADVISORY_ONLY",
        "focus": focus,
        "reason": reason,
        "next_action": next_action,
        "secondary_diagnostics": secondary_diagnostics,
        "authorization_granted": False,
        "external_action_taken": False,
        "evidence_boundary": "Internal counters and alerts only; independently verify before action.",
    }


def main() -> None:
    print(json.dumps(recommend(build()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
