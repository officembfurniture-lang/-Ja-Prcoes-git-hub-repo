#!/usr/bin/env python3
"""Read-only portfolio health report. No network, no payments, no state writes."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def build(root: Path = ROOT) -> dict:
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    counters = state["counters"]
    realized = state["realized"]
    accepted = counters["accepted"]
    paid = counters["paid"]
    last_cycle = state.get("last_cycle_result") or {}
    source_errors = last_cycle.get("source_errors") or []
    direct_readback_errors = [
        error for error in source_errors
        if isinstance(error, dict) and error.get("source") == "github_direct_readback"
    ]
    direct_attempts = int(last_cycle.get("direct_readback_attempts", 0) or 0)
    direct_captures = int(last_cycle.get("direct_readback_captures", 0) or 0)
    direct_closed = int(last_cycle.get("direct_readback_closed", 0) or 0)
    direct_404s = sum(1 for error in direct_readback_errors if error.get("http_status") == 404)
    diagnostic_alerts = (
        (["unsettled_acceptances"] if accepted > paid else [])
        + (["no_verified_conversion"] if counters["observed"] > 0 and counters["verified"] == 0 else [])
        + (["zero_direct_readback_captures"] if direct_attempts > 0 and direct_captures == 0 else [])
        + (["direct_readback_http_404"] if direct_404s > 0 else [])
    )
    return {
        "diagnostic_version": 1,
        "engine": state["engine"],
        "cycle": state["cycle"],
        "phase": state["phase"],
        "observed": counters["observed"],
        "verified": counters["verified"],
        "delivered": counters["delivered"],
        "accepted": accepted,
        "paid": paid,
        "accepted_without_verified_payment": accepted - paid,
        # Retained for backward compatibility. This is a raw counter ratio,
        # not a conversion rate: observed includes appended observation events
        # and refreshed snapshots, sometimes for the same underlying opportunity.
        "observation_to_verified_ratio": (counters["verified"] / counters["observed"] if counters["observed"] else None),
        "observation_to_verified_ratio_semantics": (
            "verified_count / appended_observation_events; NOT a conversion rate "
            "or unique-opportunity yield"
        ),
        "observation_denominator_semantics": (
            "counters.observed includes new source revisions and refreshed snapshots; "
            "the same underlying opportunity may appear in multiple observation events"
        ),
        "verified_to_delivered_ratio": (counters["delivered"] / counters["verified"] if counters["verified"] else None),
        "cash_receipt_count": len(realized["cash"]),
        "diagnostic_alerts": diagnostic_alerts,
        "last_sensor_direct_readback_attempts": direct_attempts,
        "last_sensor_direct_readback_captures": direct_captures,
        "last_sensor_direct_readback_closed": direct_closed,
        "last_sensor_direct_readback_http_404s": direct_404s,
        "last_sensor_direct_readback_error_count": len(direct_readback_errors),
        "external_cash_amount": None,
        "last_sensor_new_observations": last_cycle.get("new_observations"),
        "independent_validation": "not established by this report",
        "external_use": "not established by this report",
        "notes": [
            "Counters are internal state, not independent proof.",
            "Acceptance does not prove payment or cash received.",
            "Do not sum different currencies or infer monetary value.",
            "A sensor observation is not an earned result.",
            "The observation-to-verified ratio is a raw counter ratio, not a conversion rate; its denominator is not unique opportunities.",
            "Zero direct readback captures diagnose the last sensor cycle only; they do not establish a global source outage, source deletion, or payment status."
        ],
    }

def main() -> None:
    print(json.dumps(build(), indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
