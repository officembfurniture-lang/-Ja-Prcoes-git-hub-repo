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
        "observation_to_verified_ratio": (counters["verified"] / counters["observed"] if counters["observed"] else None),
        "verified_to_delivered_ratio": (counters["delivered"] / counters["verified"] if counters["verified"] else None),
        "cash_receipt_count": len(realized["cash"]),
        "diagnostic_alerts": (["unsettled_acceptances"] if accepted > paid else []) + (["no_verified_conversion"] if counters["observed"] > 0 and counters["verified"] == 0 else []),
        "external_cash_amount": None,
        "last_sensor_new_observations": state.get("last_cycle_result", {}).get("new_observations"),
        "independent_validation": "not established by this report",
        "external_use": "not established by this report",
        "notes": [
            "Counters are internal state, not independent proof.",
            "Acceptance does not prove payment or cash received.",
            "Do not sum different currencies or infer monetary value.",
            "A sensor observation is not an earned result.",
        ],
    }

def main() -> None:
    print(json.dumps(build(), indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
