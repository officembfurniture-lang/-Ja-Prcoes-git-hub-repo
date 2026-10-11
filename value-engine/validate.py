#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VALID_PHASES = {
    "IDLE", "SENSE", "VERIFY", "ROUTE", "SELECT", "ACQUIRE", "PRODUCE",
    "VALIDATE", "DELIVER", "OBSERVE", "SETTLE", "LEARN", "HUMAN_GATE",
    "PAYMENT_GATE_BLOCKED"
}
PRODUCTION_PHASES = {"PRODUCE", "VALIDATE", "DELIVER", "OBSERVE", "SETTLE"}
REQUIRED_GATES = (
    "primary_source_verified", "demand_or_reward_verified",
    "acceptance_criteria_known", "delivery_route_verified_before_production",
    "settlement_route_verified_before_production", "safety_and_legality_pass",
    "no_unapproved_paid_work", "no_unapproved_third_party_engagement",
)


def load(name: str):
    value = read_json((ROOT / name).read_text(encoding="utf-8"))
    require_object(value, name)
    return value


def fail(message: str) -> None:
    raise AssertionError(message)


def require_object(value, label: str) -> None:
    if not isinstance(value, dict):
        fail(f"{label} must be an object")


def require_text(value, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        fail(f"{label} must be a non-empty string")


def timestamp(value, label: str) -> datetime:
    require_text(value, label)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail(f"{label} must be an ISO timestamp")
    if result.tzinfo is None or result.utcoffset() is None:
        fail(f"{label} must include a timezone")
    return result


def positive_amount(value, label: str) -> None:
    if type(value) not in (int, float) or value <= 0:
        fail(f"{label} must be a positive finite number")
    if isinstance(value, float) and not math.isfinite(value):
        fail(f"{label} must be a positive finite number")


def read_json(text: str):
    def reject_constant(value):
        fail(f"non-finite JSON constant: {value}")

    return json.loads(text, parse_constant=reject_constant)


def validate_ndjson(name: str) -> list[dict]:
    path = ROOT / name
    if not path.exists():
        return []
    rows = []
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = read_json(line)
            require_object(row, f"{name}:{idx}")
            rows.append(row)
        except json.JSONDecodeError as exc:
            fail(f"{name}:{idx}: invalid JSON: {exc}")
    return rows


def validate_outcomes(rows: list[dict], counters: dict) -> None:
    """Check receipt structure, not authenticity or an external account balance."""
    paid_ids = set()
    for idx, row in enumerate(rows, 1):
        label = f"outcomes.ndjson:{idx}"
        require_text(row.get("opportunity_id"), f"{label}.opportunity_id")
        require_text(row.get("status"), f"{label}.status")
        if row["status"] not in {"ACCEPTED", "PAID"}:
            continue
        positive_amount(row.get("amount"), f"{label}.amount")
        for key in ("currency", "delivery_evidence", "acceptance_evidence"):
            require_text(row.get(key), f"{label}.{key}")
        accepted = timestamp(row.get("accepted_at"), f"{label}.accepted_at")
        if row["status"] == "PAID":
            require_text(row.get("payment_evidence"), f"{label}.payment_evidence")
            received = timestamp(row.get("received_at"), f"{label}.received_at")
            if received < accepted:
                fail(f"{label}: payment predates acceptance")
            if row["opportunity_id"] in paid_ids:
                fail(f"{label}: duplicate PAID receipt for opportunity")
            paid_ids.add(row["opportunity_id"])
    if counters["paid"] != len(paid_ids):
        fail("paid counter must match distinct PAID opportunity receipts")


def validate_sensor_history(state: dict, observations: list[dict],
                            ledger: list[dict], *, present: bool,
                            observation_bytes: bytes | None = None) -> None:
    """Cross-reconcile sensor receipts and captured records, without external claims.

    The production entrypoint requires both append-only stores. The pure
    helper is separately testable with a synthetic in-memory history.
    """
    if not present:
        return
    completed = 0
    appended = 0
    most_recent = None
    for index, row in enumerate(ledger, 1):
        label = f"run-ledger.ndjson:{index}"
        result = row.get("result")
        if result == "LEASE_BUSY":
            continue  # An idle/blocked duplicate did not append observations.
        if result != "SENSE_COMPLETE":
            fail(f"{label}: unexpected sensor result {result!r}")
        completed += 1
        require_text(row.get("cycle_id"), f"{label}.cycle_id")
        prefix = f"cycle-{completed}-"
        if not row["cycle_id"].startswith(prefix) or row["cycle_id"] == prefix:
            fail(f"{label}: missing or reordered completed sensor cycle")
        for field in ("new_observations", "refreshed_snapshots"):
            value = row.get(field, 0 if field == "refreshed_snapshots" else None)
            if type(value) is not int or value < 0:
                fail(f"{label}.{field} must be a non-negative integer")
        if row.get("realized_value") != 0 or type(row.get("realized_value")) is not int:
            fail(f"{label}: sensor must never record realized value")
        appended += row["new_observations"] + row.get("refreshed_snapshots", 0)
        most_recent = row

    if completed != state["cycle"]:
        fail("state.cycle must match completed run-ledger cycles")
    if appended != len(observations):
        fail("observation row count differs from append-only sensor ledger")
    if appended != state["counters"]["observed"]:
        fail("observed counter differs from append-only sensor ledger")

    if most_recent is not None:
        last = state.get("last_cycle_result")
        require_object(last, "state.last_cycle_result")
        if (last.get("cycle_id") != most_recent.get("cycle_id")
                or last.get("at") != most_recent.get("at")
                or last.get("source_errors") != most_recent.get("errors")
                or last.get("new_observations") != most_recent.get("new_observations")
                or last.get("refreshed_snapshots", 0)
                    != most_recent.get("refreshed_snapshots", 0)):
            fail("last sensor state does not reconcile with ledger receipt")

        # Backward-compatible with completed pre-checkpoint cycles. Once a
        # sensor emits a digest it must be present in both receipts and match
        # the exact byte stream that triage will later read.
        state_digest = last.get("observations_sha256")
        ledger_digest = most_recent.get("observations_sha256")
        if state_digest is not None or ledger_digest is not None:
            if (not isinstance(state_digest, str)
                    or not isinstance(ledger_digest, str)
                    or len(state_digest) != 64
                    or any(ch not in "0123456789abcdef" for ch in state_digest)
                    or state_digest != ledger_digest):
                fail("observation digest missing, malformed or inconsistent")
            if observation_bytes is None:
                fail("observation bytes required for content-anchor validation")
            if hashlib.sha256(observation_bytes).hexdigest() != ledger_digest:
                fail("observation content checksum differs from last completed cycle")


def active_payment_liability(state: dict) -> bool:
    active = state.get("active_opportunity")
    return isinstance(active, dict) and (active.get("paid_work_commissioned") is True or active.get("financial_obligation_authorized") is True)

def main() -> int:
    state = load("state.json")
    policy = load("policy.json")
    routes = load("routes.json")
    sources = load("sources.json")

    if state.get("engine") != "VALUE_ENGINE_v2":
        fail("unexpected engine identifier")
    if not isinstance(state.get("phase"), str) or state["phase"] not in VALID_PHASES:
        fail(f"invalid phase: {state.get('phase')}")

    lease = state.get("lease")
    require_object(lease, "lease")
    lease_values = [lease.get("cycle_id"), lease.get("owner"), lease.get("acquired_at"), lease.get("expires_at")]
    populated = [value is not None for value in lease_values]
    if any(populated) and not all(populated):
        fail("lease must be fully populated or fully empty")
    if all(populated):
        require_text(lease["cycle_id"], "lease.cycle_id")
        require_text(lease["owner"], "lease.owner")
        acquired = timestamp(lease["acquired_at"], "lease.acquired_at")
        expires = timestamp(lease["expires_at"], "lease.expires_at")
        if expires <= acquired:
            fail("lease expiry must be after acquisition")
    if state.get("phase") == "PAYMENT_GATE_BLOCKED" and active_payment_liability(state):
        fail("blocked payment state must not retain an active payable engagement")
    if state.get("phase") == "IDLE" and any(populated):
        fail("IDLE state may not retain an active lease")

    if state.get("phase") == "IDLE" and state.get("active_opportunity") is not None:
        fail("IDLE may not contain active_opportunity")
    if state.get("phase") == "IDLE" and state.get("active_route") is not None:
        fail("IDLE may not contain active_route")

    counters = state.get("counters", {})
    require_object(counters, "counters")
    required = ["observed", "verified", "selected", "produced", "delivered", "accepted", "paid", "human_gates"]
    for key in required:
        value = counters.get(key)
        if type(value) is not int or value < 0:
            fail(f"counter {key} must be a non-negative integer")

    if not (counters["paid"] <= counters["accepted"] <= counters["delivered"] <= counters["produced"] <= counters["selected"] <= counters["verified"] <= counters["observed"]):
        fail("counter ordering invariant violated")

    realized = state.get("realized", {})
    require_object(realized, "realized")
    for bucket in ("cash", "verified_non_cash", "cost_savings"):
        if not isinstance(realized.get(bucket), list):
            fail(f"realized.{bucket} must be a list")
    for payment in realized.get("cash", []):
        require_object(payment, "cash realization")
        positive_amount(payment.get("amount"), "cash realization.amount")
        for field in ("currency", "evidence"):
            require_text(payment.get(field), f"cash realization.{field}")
        timestamp(payment.get("received_at"), "cash realization.received_at")

    hard_gates = policy.get("hard_gates", {})
    require_object(hard_gates, "policy.hard_gates")
    for required_gate in REQUIRED_GATES:
        if hard_gates.get(required_gate) is not True:
            fail(f"hard gate weakened or missing: {required_gate}")

    route_items = routes.get("routes")
    if not isinstance(route_items, list):
        fail("routes.routes must be a list")
    for route in route_items:
        require_object(route, "route")
        require_text(route.get("id"), "route.id")
    route_ids = [r["id"] for r in route_items]
    if len(route_ids) != len(set(route_ids)):
        fail("route ids must be unique")
    if "human_gate" not in route_ids or "github_actions_public_http" not in route_ids:
        fail("required fallback routes missing")

    source_items = sources.get("sources")
    if not isinstance(source_items, list):
        fail("sources.sources must be a list")
    for source in source_items:
        require_object(source, "source")
        require_text(source.get("id"), "source.id")
    source_ids = [s["id"] for s in source_items]
    if len(source_ids) != len(set(source_ids)):
        fail("source ids must be unique")
    if len(source_ids) < 3:
        fail("engine must not collapse discovery to one source class")

    active = state.get("active_opportunity")
    if active is not None:
        require_object(active, "active_opportunity")
    if state["phase"] in PRODUCTION_PHASES:
        require_object(active, "production active_opportunity")
        require_text(active.get("id"), "active_opportunity.id")
        if not all(populated):
            fail("production requires a fully populated lease")
        for gate in REQUIRED_GATES:
            if active.get(gate) is not True:
                fail(f"active opportunity has not passed hard gate: {gate}")
        by_id = {route["id"]: route for route in route_items}
        for field, kinds in (
            ("delivery_route", {"delivery", "delivery_and_settlement", "dynamic"}),
            ("settlement_route", {"settlement", "delivery_and_settlement", "dynamic"}),
        ):
            require_text(active.get(field), f"active_opportunity.{field}")
            route = by_id.get(active[field])
            if route is None:
                fail(f"unknown {field}: {active[field]}")
            if route.get("kind") not in kinds or route.get("selectable_for_execution") is False:
                fail(f"{field} does not support execution: {active[field]}")

    observations_exist = (ROOT / "observations.ndjson").exists()
    ledger_exists = (ROOT / "run-ledger.ndjson").exists()
    if not observations_exist or not ledger_exists:
        fail("both sensor observation and run-ledger stores are required")
    observations = validate_ndjson("observations.ndjson")
    ledger = validate_ndjson("run-ledger.ndjson")
    validate_sensor_history(
        state, observations, ledger, present=observations_exist,
        observation_bytes=(ROOT / "observations.ndjson").read_bytes(),
    )
    validate_outcomes(validate_ndjson("outcomes.ndjson"), counters)
    print("VALUE_ENGINE invariants: OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AssertionError, json.JSONDecodeError) as exc:
        print(f"VALUE_ENGINE validation failed: {exc}", file=sys.stderr)
        sys.exit(1)
