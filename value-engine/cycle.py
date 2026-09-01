#!/usr/bin/env python3
"""Deterministic VALUE_ENGINE sensor.

This process does not select or execute work. It keeps the engine alive when the
semantic worker is unavailable: acquires a lease, senses public demand signals,
persists observations, and releases the lease. Selection requires later VERIFY
and ROUTE gates with real delivery + settlement paths.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state.json"
SOURCES = ROOT / "sources.json"
OBS = ROOT / "observations.ndjson"
RUNS = ROOT / "run-ledger.ndjson"


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_ndjson(path: Path, records: list[dict]) -> None:
    if not records:
        return
    with path.open("a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def existing_fingerprints() -> set[str]:
    if not OBS.exists():
        return set()
    out: set[str] = set()
    for line in OBS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.add(json.loads(line)["fingerprint"])
            except (KeyError, json.JSONDecodeError):
                pass
    return out


def github_search(query: str, token: str | None) -> list[dict]:
    params = urllib.parse.urlencode({"q": query, "sort": "updated", "order": "desc", "per_page": 10})
    url = f"https://api.github.com/search/issues?{params}"

    def request(use_token: bool):
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "value-engine-v2",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if use_token and token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        return request(True).get("items", [])
    except urllib.error.HTTPError as exc:
        if token and exc.code in (401, 403):
            return request(False).get("items", [])
        raise


def normalize(item: dict, query: str, detected_at: str) -> dict:
    raw = "|".join([str(item.get("id")), item.get("html_url", ""), item.get("updated_at", "")])
    fingerprint = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    body = (item.get("body") or "")[:4000]
    return {
        "fingerprint": fingerprint,
        "source": "github_public_demand",
        "signal_query": query,
        "external_id": item.get("id"),
        "url": item.get("html_url"),
        "title": item.get("title"),
        "body_excerpt": body,
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "detected_at": detected_at,
        "status": "OBSERVED",
        "primary_source_verified": False,
        "demand_or_reward_verified": False,
        "delivery_route": None,
        "settlement_route": None,
        "realized_value": 0,
    }


def main() -> int:
    state = read_json(STATE)
    source_cfg = read_json(SOURCES)
    current = now()
    current_iso = iso(current)

    lease = state.get("lease") or {}
    expires = parse_time(lease.get("expires_at"))
    if expires and expires > current:
        append_ndjson(RUNS, [{
            "at": current_iso,
            "result": "LEASE_BUSY",
            "cycle": state.get("cycle", 0),
            "lease_owner": lease.get("owner"),
            "lease_expires_at": lease.get("expires_at"),
        }])
        return 0

    cycle = int(state.get("cycle", 0)) + 1
    run_id = os.getenv("GITHUB_RUN_ID") or f"local-{int(current.timestamp())}"
    cycle_id = f"cycle-{cycle}-{run_id}"
    owner = f"github-actions:{run_id}" if os.getenv("GITHUB_ACTIONS") else f"local:{run_id}"
    state["cycle"] = cycle
    state["phase"] = "SENSE"
    state["lease"] = {
        "cycle_id": cycle_id,
        "owner": owner,
        "acquired_at": current_iso,
        "expires_at": iso(current + timedelta(minutes=45)),
    }
    write_json(STATE, state)

    token = os.getenv("GITHUB_TOKEN")
    known = existing_fingerprints()
    new_records: list[dict] = []
    errors: list[dict] = []

    for source in source_cfg.get("sources", []):
        if not source.get("enabled") or source.get("adapter") != "github_issue_search":
            continue
        for query in source.get("queries", []):
            try:
                for item in github_search(query, token):
                    record = normalize(item, query, current_iso)
                    if record["fingerprint"] not in known:
                        known.add(record["fingerprint"])
                        new_records.append(record)
            except Exception as exc:  # record failure; do not fabricate observations
                errors.append({"source": source.get("id"), "query": query, "error": type(exc).__name__})

    append_ndjson(OBS, new_records)
    counters = state.setdefault("counters", {})
    counters["observed"] = int(counters.get("observed", 0)) + len(new_records)
    state["phase"] = "IDLE"
    state["lease"] = {"cycle_id": None, "owner": None, "acquired_at": None, "expires_at": None}
    state["last_transition"] = "SENSE -> IDLE"
    state["last_cycle_result"] = {
        "cycle_id": cycle_id,
        "at": current_iso,
        "new_observations": len(new_records),
        "source_errors": errors,
        "selected": 0,
        "delivered": 0,
        "paid": 0,
        "note": "Sensor cycle only; observations are not value and require VERIFY + ROUTE before execution."
    }
    write_json(STATE, state)
    append_ndjson(RUNS, [{
        "at": current_iso,
        "cycle_id": cycle_id,
        "result": "SENSE_COMPLETE",
        "new_observations": len(new_records),
        "errors": errors,
        "realized_value": 0,
    }])
    print(f"VALUE_ENGINE {cycle_id}: {len(new_records)} new observations, {len(errors)} source errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
