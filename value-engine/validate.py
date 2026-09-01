#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VALID_PHASES = {
    "IDLE", "SENSE", "VERIFY", "ROUTE", "SELECT", "ACQUIRE", "PRODUCE",
    "VALIDATE", "DELIVER", "OBSERVE", "SETTLE", "LEARN", "HUMAN_GATE"
}


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def fail(message: str) -> None:
    raise AssertionError(message)


def validate_ndjson(name: str) -> None:
    path = ROOT / name
    if not path.exists():
        return
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError as exc:
            fail(f"{name}:{idx}: invalid JSON: {exc}")


def main() -> int:
    state = load("state.json")
    policy = load("policy.json")
    routes = load("routes.json")
    sources = load("sources.json")

    if state.get("engine") != "VALUE_ENGINE_v2":
        fail("unexpected engine identifier")
    if state.get("phase") not in VALID_PHASES:
        fail(f"invalid phase: {state.get('phase')}")

    lease = state.get("lease") or {}
    lease_values = [lease.get("cycle_id"), lease.get("owner"), lease.get("acquired_at"), lease.get("expires_at")]
    if any(lease_values) and not all(lease_values):
        fail("lease must be fully populated or fully empty")
    if state.get("phase") == "IDLE" and any(lease_values):
        fail("IDLE state may not retain an active lease")

    if state.get("phase") == "IDLE" and state.get("active_opportunity") is not None:
        fail("IDLE may not contain active_opportunity")

    counters = state.get("counters", {})
    required = ["observed", "verified", "selected", "produced", "delivered", "accepted", "paid", "human_gates"]
    for key in required:
        value = counters.get(key)
        if not isinstance(value, int) or value < 0:
            fail(f"counter {key} must be a non-negative integer")

    if not (counters["paid"] <= counters["accepted"] <= counters["delivered"] <= counters["produced"] <= counters["selected"] <= counters["verified"] <= counters["observed"]):
        fail("counter ordering invariant violated")

    realized = state.get("realized", {})
    for bucket in ("cash", "verified_non_cash", "cost_savings"):
        if not isinstance(realized.get(bucket), list):
            fail(f"realized.{bucket} must be a list")
    for payment in realized.get("cash", []):
        for field in ("amount", "currency", "evidence", "received_at"):
            if not payment.get(field):
                fail(f"cash realization missing {field}")

    hard_gates = policy.get("hard_gates", {})
    for required_gate in (
        "primary_source_verified", "demand_or_reward_verified",
        "acceptance_criteria_known", "delivery_route_verified_before_production",
        "settlement_route_verified_before_production", "safety_and_legality_pass"
    ):
        if hard_gates.get(required_gate) is not True:
            fail(f"hard gate weakened or missing: {required_gate}")

    route_ids = [r.get("id") for r in routes.get("routes", [])]
    if len(route_ids) != len(set(route_ids)) or None in route_ids:
        fail("route ids must be unique and non-null")
    if "human_gate" not in route_ids or "github_actions_public_http" not in route_ids:
        fail("required fallback routes missing")

    source_ids = [s.get("id") for s in sources.get("sources", [])]
    if len(source_ids) != len(set(source_ids)) or None in source_ids:
        fail("source ids must be unique and non-null")
    if len(source_ids) < 3:
        fail("engine must not collapse discovery to one source class")

    active = state.get("active_opportunity")
    if active and state.get("phase") in {"PRODUCE", "VALIDATE", "DELIVER", "OBSERVE", "SETTLE"}:
        if not active.get("delivery_route") or not active.get("settlement_route"):
            fail("active work reached production without delivery+settlement route")

    validate_ndjson("observations.ndjson")
    validate_ndjson("run-ledger.ndjson")
    print("VALUE_ENGINE invariants: OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"VALUE_ENGINE validation failed: {exc}", file=sys.stderr)
        sys.exit(1)
