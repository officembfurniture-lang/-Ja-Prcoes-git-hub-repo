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
import re
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


# Re-read an unchanged source revision before triage's seven-day snapshot gate.
# A repeated GitHub GET is a new OBSERVED snapshot, not a new opportunity.
SNAPSHOT_REFRESH_AFTER = timedelta(days=6)
MAX_DIRECT_READBACKS = 3
DIRECT_FAILURE_COOLDOWN = timedelta(hours=24)
ISSUE_URL_RE = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/issues/([1-9][0-9]*)\Z")


def existing_snapshots() -> dict[str, datetime | None]:
    """Last captured readback per source revision, preserving append-only history."""
    if not OBS.exists():
        return {}
    latest: dict[str, datetime | None] = {}
    for line in OBS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            fingerprint = record["fingerprint"]
        except (TypeError, KeyError, json.JSONDecodeError):
            continue
        if not isinstance(fingerprint, str) or not fingerprint:
            continue
        try:
            detected = parse_time(record.get("detected_at"))
            if detected is None or detected.utcoffset() is None:
                detected = None
            else:
                detected = detected.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError, AttributeError):
            detected = None
        old = latest.get(fingerprint)
        if fingerprint not in latest or (
            detected is not None and (old is None or detected > old)
        ):
            latest[fingerprint] = detected
    return latest


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


def github_issue_readback(url: str, token: str | None) -> dict:
    """Read one strict GitHub issue URL. No arbitrary URL fetches or writes."""
    match = ISSUE_URL_RE.fullmatch(url)
    if match is None:
        raise ValueError("not_an_allowed_github_issue_url")
    owner, repository, number = match.groups()
    endpoint = f"https://api.github.com/repos/{owner}/{repository}/issues/{number}"

    def request(use_token: bool):
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "value-engine-v2-direct-readback",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if use_token and token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(endpoint, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not isinstance(result, dict):
            raise ValueError("invalid_issue_response")
        return result

    try:
        return request(True)
    except urllib.error.HTTPError as exc:
        if token and exc.code in (401, 403):
            return request(False)
        raise


def recent_failed_direct_readbacks(current: datetime) -> set[str]:
    """Durable 24h retry budget from canonical run-ledger error receipts."""
    failed: set[str] = set()
    if not RUNS.exists():
        return failed
    for line in RUNS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            stamp = parse_time(row.get("at"))
            if stamp is None or stamp.utcoffset() is None:
                continue
            age = current - stamp.astimezone(timezone.utc)
            if age < timedelta(0) or age >= DIRECT_FAILURE_COOLDOWN:
                continue
            for error in row.get("errors", []):
                if isinstance(error, dict) and error.get("source") == "github_direct_readback":
                    url = error.get("url")
                    if isinstance(url, str) and ISSUE_URL_RE.fullmatch(url):
                        failed.add(url)
        except (ValueError, TypeError, AttributeError, json.JSONDecodeError, OverflowError):
            continue
    return failed


def select_direct_readbacks(current: datetime, known: dict[str, datetime | None],
                            search_seen_urls: set[str],
                            excluded_urls: set[str] | None = None) -> list[dict]:
    """Rank stale stored candidates for a fresh public issue readback only."""
    if not OBS.exists():
        return []
    from triage import classify, iter_records, newest_by_url

    candidates = []
    excluded_urls = excluded_urls or set()
    for record in newest_by_url(iter_records(OBS)):
        url = record.get("url")
        if record.get("source") != "github_public_demand" or not isinstance(url, str):
            continue
        if (ISSUE_URL_RE.fullmatch(url) is None or url in search_seen_urls
                or url in excluded_urls):
            continue
        fingerprint = record.get("fingerprint")
        if not isinstance(fingerprint, str):
            continue
        last_seen = known.get(fingerprint)
        if last_seen is not None and (last_seen > current
                                      or current - last_seen < SNAPSHOT_REFRESH_AFTER):
            continue
        classification = classify(record, current)
        if classification["disposition"] != "HOLD_STALE_OBSERVATION":
            continue
        candidates.append((-classification["triage_score"], url, record))
    return [record for _, _, record in sorted(candidates)]


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
        "source_state": item.get("state"),
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
    known = existing_snapshots()
    new_records: list[dict] = []
    refreshed_records: list[dict] = []
    errors: list[dict] = []
    search_seen_urls: set[str] = set()
    direct_attempts = 0
    direct_captures = 0
    direct_closed = 0

    for source in source_cfg.get("sources", []):
        if not source.get("enabled") or source.get("adapter") != "github_issue_search":
            continue
        for query in source.get("queries", []):
            try:
                for item in github_search(query, token):
                    record = normalize(item, query, current_iso)
                    search_seen_urls.add(str(record.get("url") or ""))
                    fingerprint = record["fingerprint"]
                    if fingerprint not in known:
                        new_records.append(record)
                    else:
                        last_readback = known[fingerprint]
                        if (last_readback is None or last_readback > current
                                or current - last_readback >= SNAPSHOT_REFRESH_AFTER):
                            refreshed_records.append(record)
                        else:
                            continue
                    # Deduplicate across overlapping search queries in this run.
                    known[fingerprint] = current
            except Exception as exc:  # record failure; do not fabricate observations
                errors.append({"source": source.get("id"), "query": query, "error": type(exc).__name__})

    # Historical candidates not returned by recent searches: at most three
    # read-only GitHub GETs per cycle; no contact, claim, execution or payment.
    cooldown_urls = recent_failed_direct_readbacks(current)
    for candidate in select_direct_readbacks(current, known, search_seen_urls,
                                              cooldown_urls):
        if direct_attempts >= MAX_DIRECT_READBACKS:
            break
        direct_attempts += 1
        url = candidate["url"]
        try:
            live = github_issue_readback(url, token)
            if (live.get("html_url") != url
                    or (candidate.get("external_id") is not None
                        and live.get("id") != candidate["external_id"])
                    or live.get("state") not in ("open", "closed")
                    or "pull_request" in live):
                raise ValueError("source_identity_or_state_mismatch")
            record = normalize(live, candidate.get("signal_query") or "direct_readback", current_iso)
            fingerprint = record["fingerprint"]
            if fingerprint not in known:
                new_records.append(record)
            else:
                last_readback = known[fingerprint]
                if (last_readback is None or last_readback > current
                        or current - last_readback >= SNAPSHOT_REFRESH_AFTER):
                    refreshed_records.append(record)
                else:
                    continue
            known[fingerprint] = current
            direct_captures += 1
            if live["state"] == "closed":
                direct_closed += 1
        except Exception as exc:
            # HTTP failures and mismatched identities never refresh an observation.
            errors.append({"source": "github_direct_readback", "url": url,
                           "error": type(exc).__name__,
                           "http_status": exc.code if isinstance(exc, urllib.error.HTTPError) else None})

    append_ndjson(OBS, new_records + refreshed_records)
    counters = state.setdefault("counters", {})
    counters["observed"] = int(counters.get("observed", 0)) + len(new_records) + len(refreshed_records)
    state["phase"] = "IDLE"
    state["lease"] = {"cycle_id": None, "owner": None, "acquired_at": None, "expires_at": None}
    state["last_transition"] = "SENSE -> IDLE"
    state["last_cycle_result"] = {
        "cycle_id": cycle_id,
        "at": current_iso,
        "new_observations": len(new_records),
        "refreshed_snapshots": len(refreshed_records),
        "direct_readback_attempts": direct_attempts,
        "direct_readback_captures": direct_captures,
        "direct_readback_closed": direct_closed,
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
        "refreshed_snapshots": len(refreshed_records),
        "direct_readback_attempts": direct_attempts,
        "direct_readback_captures": direct_captures,
        "direct_readback_closed": direct_closed,
        "errors": errors,
        "realized_value": 0,
    }])
    print(f"VALUE_ENGINE {cycle_id}: {len(new_records)} new revisions, "
          f"{len(refreshed_records)} refreshed snapshots, {len(errors)} source errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
