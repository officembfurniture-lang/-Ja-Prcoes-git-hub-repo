#!/usr/bin/env python3
"""Deterministic pre-VERIFY triage for VALUE_ENGINE.

This stage reduces the OBSERVED backlog to a small semantic VERIFY queue. It is
strictly non-authoritative: it never marks an opportunity VERIFIED, never
selects work, never executes external actions, and never changes realized-value
accounting. Its only job is to rank/hold/drop observations with explicit reasons.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent
DEFAULT_OBS = ROOT / "observations.ndjson"
DEFAULT_QUEUE = ROOT / "triage-queue.ndjson"
DEFAULT_SUMMARY = ROOT / "triage-summary.json"

VALUE_RE = re.compile(
    r"(?:\$\s?\d[\d,.]*|\b\d[\d,.]*\s?(?:USD|USDC|EUR|GBP|sats?|RTC)\b)",
    re.IGNORECASE,
)

MIRROR_MARKERS = (
    "bounty-plaza",
    "bountyscout",
    "sn-monetization-runtime",
    "radar]",
    "bounty alert",
)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def text_of(record: dict) -> str:
    return "\n".join(
        str(record.get(key) or "")
        for key in ("title", "body_excerpt", "signal_query", "url")
    ).lower()


def phrase(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def classify(record: dict, reference_time: datetime) -> dict:
    text = text_of(record)
    reasons: list[str] = []
    risks: list[str] = []
    score = 0

    amounts = VALUE_RE.findall(text)
    if amounts:
        score += 4
        reasons.append("explicit_value_mention")

    if phrase(text, "bounty", "reward", "paid task", "prize", "grant"):
        score += 2
        reasons.append("explicit_demand_signal")

    if phrase(text, "funded", "escrowed", "funding confirmed", "funding:"):
        score += 4
        reasons.append("funding_language_present")

    if phrase(text, "acceptance criteria", "acceptance:", "requirements", "deliverables"):
        score += 3
        reasons.append("acceptance_surface_present")

    if phrase(text, "autonomous agents", "agents welcome", "agent-native", "ai-assisted"):
        score += 2
        reasons.append("agent_compatibility_signal")

    if phrase(text, "submit a pr", "submit a pull request", "pull request", "/opire try", "/claim"):
        score += 2
        reasons.append("delivery_route_language_present")

    if phrase(text, "payment is released", "payout", "settlement", "paid on merge", "payment is made"):
        score += 2
        reasons.append("settlement_language_present")

    updated = parse_time(record.get("updated_at")) or parse_time(record.get("created_at"))
    if updated:
        age_days = max(0.0, (reference_time - updated).total_seconds() / 86400.0)
        if age_days <= 7:
            score += 3
            reasons.append("fresh_7d")
        elif age_days <= 30:
            score += 1
            reasons.append("fresh_30d")
        else:
            risks.append("stale_over_30d")
            score -= 3
    else:
        risks.append("freshness_unknown")

    if phrase(
        text,
        "proposed bounty",
        "bounty proposal",
        "proposed reward",
        "please confirm whether",
        "not a claim of an existing funded bounty",
    ):
        risks.append("reward_not_yet_confirmed")
        score -= 7

    if phrase(
        text,
        "do not start",
        "do not claim",
        "do not sign",
        "incomplete mirror",
        "excluded from solver",
    ):
        risks.append("explicit_start_prohibition")
        score -= 20

    if phrase(
        text,
        "sign up",
        "signup",
        "maintainer must confirm",
        "wait for confirmation",
        "upon confirmation",
    ):
        risks.append("human_gate_required")
        score -= 4

    if phrase(
        text,
        "claim bond",
        "entry bond",
        "stake required",
        "security deposit",
        "self-funded",
        "fully fund that child",
        "entry fee",
    ):
        risks.append("capital_required")
        score -= 8

    if any(marker in text for marker in MIRROR_MARKERS):
        risks.append("mirror_or_radar_source")
        score -= 12

    if "primary_source_verified\": true" in text:
        # Do not trust self-asserted serialized flags from mirrors as verification.
        risks.append("self_asserted_verification_only")

    if "explicit_start_prohibition" in risks:
        disposition = "HOLD_START_PROHIBITED"
    elif "mirror_or_radar_source" in risks:
        disposition = "HOLD_PRIMARY_SOURCE"
    elif "capital_required" in risks:
        disposition = "HOLD_CAPITAL_REQUIRED"
    elif "human_gate_required" in risks:
        disposition = "HOLD_HUMAN_GATE"
    elif "reward_not_yet_confirmed" in risks:
        disposition = "HOLD_REWARD_UNCONFIRMED"
    elif score >= 8:
        disposition = "QUEUE_VERIFY"
    else:
        disposition = "DROP_LOW_SIGNAL"

    return {
        "fingerprint": record.get("fingerprint"),
        "url": record.get("url"),
        "title": record.get("title"),
        "detected_at": record.get("detected_at"),
        "updated_at": record.get("updated_at"),
        "source": record.get("source"),
        "signal_query": record.get("signal_query"),
        "triage_score": score,
        "disposition": disposition,
        "reasons": reasons,
        "risks": risks,
        "amount_mentions": amounts[:8],
        "status": "OBSERVED",
        "primary_source_verified": False,
        "demand_or_reward_verified": False,
        "realized_value": 0,
    }


def iter_records(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid NDJSON at line {line_number}") from exc
            if isinstance(value, dict):
                yield value


def newest_by_url(records: Iterable[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for record in records:
        key = str(record.get("url") or record.get("fingerprint") or "")
        if not key:
            continue
        current = latest.get(key)
        if current is None:
            latest[key] = record
            continue
        new_time = parse_time(record.get("detected_at")) or datetime.min.replace(tzinfo=timezone.utc)
        old_time = parse_time(current.get("detected_at")) or datetime.min.replace(tzinfo=timezone.utc)
        if new_time >= old_time:
            latest[key] = record
    return list(latest.values())


def reference_time(records: list[dict]) -> datetime:
    times = [parse_time(r.get("detected_at")) for r in records]
    known = [t for t in times if t is not None]
    return max(known) if known else datetime.now(timezone.utc)


def run(observations: Path, queue_path: Path, summary_path: Path, limit: int) -> dict:
    records = newest_by_url(iter_records(observations))
    ref = reference_time(records)
    triaged = [classify(record, ref) for record in records]
    verify = sorted(
        (item for item in triaged if item["disposition"] == "QUEUE_VERIFY"),
        key=lambda item: (-item["triage_score"], item.get("updated_at") or ""),
    )[:limit]

    with queue_path.open("w", encoding="utf-8") as handle:
        for item in verify:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    counts = Counter(item["disposition"] for item in triaged)
    summary = {
        "engine": "VALUE_ENGINE_v2",
        "stage": "PRE_VERIFY_TRIAGE",
        "reference_time": ref.isoformat().replace("+00:00", "Z"),
        "unique_observations": len(records),
        "verify_queue_total": sum(1 for item in triaged if item["disposition"] == "QUEUE_VERIFY"),
        "verify_queue_emitted": len(verify),
        "dispositions": dict(sorted(counts.items())),
        "authoritative": False,
        "note": "Triage is not verification, selection, execution, delivery, settlement, or realized value.",
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observations", type=Path, default=DEFAULT_OBS)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be >= 1")
    summary = run(args.observations, args.queue, args.summary, args.limit)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
