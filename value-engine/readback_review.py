#!/usr/bin/env python3
"""Fail-closed, read-only decisions from a bound queue and direct GET receipts.

This is *pre-VERIFY* guidance, not verification, selection, work authorization,
funding evidence, financial realization or automatic source-state persistence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from cycle import ISSUE_URL_RE
from source_probe import MAX_SOURCE_BODY_CHARS
from triage import classify, parse_time

SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
MAX_GETS = 3
NO_AUTHORITY = {
    "primary_source_verified": False,
    "demand_or_reward_verified": False,
    "settlement_route_verified": False,
    "authorization_to_execute": False,
    "realized_value": 0,
}
REVIEW_POLICY = {
    "READBACK_CLOSED": ("HOLD_CLOSED_SOURCE", "Do not pursue this closed issue as an open offer."),
    "READBACK_FAILED": ("HOLD_SOURCE_UNCONFIRMED", "Retry or inspect source; failure is not proof of closure."),
}
# These are conservative stop/hold reasons from the established triage
# classifier, not external authorization decisions or funding verification.
CURRENT_SOURCE_HOLDS = frozenset({
    "HOLD_START_PROHIBITED", "HOLD_CAPITAL_REQUIRED", "HOLD_HUMAN_GATE",
    "HOLD_DEPENDENCIES", "HOLD_REWARD_UNCONFIRMED", "HOLD_PRIMARY_SOURCE",
    "HOLD_SOURCE_CLOSED",
})


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def records(raw: bytes, label: str) -> list[dict]:
    try:
        result = []
        for i, line in enumerate(raw.decode("utf-8").splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{label}:{i}: expected object")
            result.append(value)
        return result
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}: invalid NDJSON") from exc


def object_json(raw: bytes, label: str) -> dict:
    try:
        result = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}: invalid JSON") from exc
    if not isinstance(result, dict):
        raise ValueError(f"{label}: expected object")
    return result


def deny_authority(value: dict, label: str) -> None:
    if (value.get("authoritative", False) is not False
            or type(value.get("realized_value")) is not int):
        raise ValueError(f"{label}: false authority or invalid value type")
    for key, expected in NO_AUTHORITY.items():
        if value.get(key) is not expected and (
            not (key == "realized_value" and type(value.get(key)) is int
                 and value.get(key) == expected)
        ):
            raise ValueError(f"{label}: {key} must remain non-authoritative")


def review(queue_data: bytes, receipt_data: bytes, probe_data: bytes) -> tuple[list[dict], dict]:
    queue = records(queue_data, "queue")
    receipts = records(receipt_data, "readbacks")
    probe = object_json(probe_data, "probe summary")
    if (probe.get("schema") != "value-engine.source-readback/v1"
            or probe.get("stage") != "SOURCE_READBACK_NON_AUTHORITATIVE"
            or probe.get("queue_sha256") != sha256(queue_data)
            or type(probe.get("queue_count")) is not int
            or probe["queue_count"] != len(queue)
            or type(probe.get("attempted")) is not int
            or type(probe.get("results")) is not int
            or probe["attempted"] != len(receipts)
            or probe["results"] != len(receipts)
            or len(receipts) > MAX_GETS
            or not isinstance(probe.get("readback_at"), str)
            or not probe["readback_at"]):
        raise ValueError("readback summary does not bind this queue and receipt set")
    deny_authority(probe, "probe summary")
    expected_dispositions = dict(sorted(Counter(x.get("status") for x in receipts).items()))
    if probe.get("dispositions") != expected_dispositions:
        raise ValueError("readback disposition counts mismatch")

    decisions = []
    seen_ranks = set()
    for receipt in receipts:
        deny_authority(receipt, "readback receipt")
        rank = receipt.get("queue_rank")
        if type(rank) is not int or not 1 <= rank <= len(queue) or rank in seen_ranks:
            raise ValueError("invalid/duplicate queue rank")
        seen_ranks.add(rank)
        queued = queue[rank - 1]
        url = queued.get("url")
        if (not isinstance(url, str) or ISSUE_URL_RE.fullmatch(url) is None
                or queued.get("disposition") != "QUEUE_VERIFY"
                or queued.get("status") != "OBSERVED"
                or not isinstance(queued.get("fingerprint"), str)
                or not queued["fingerprint"]
                or receipt.get("queue_source_url") != url
                or receipt.get("queue_fingerprint") != queued["fingerprint"]
                or receipt.get("queue_title") != queued.get("title")
                or receipt.get("queue_source_updated_at") != queued.get("updated_at")
                or receipt.get("readback_at") != probe["readback_at"]):
            raise ValueError("readback source identity does not match bound queue")

        source_status = receipt.get("status")
        current_policy = None
        current_risks = []
        if source_status in ("READBACK_OPEN", "READBACK_CLOSED"):
            title = receipt.get("source_title")
            excerpt = receipt.get("source_body_excerpt")
            truncated = receipt.get("source_body_truncated")
            updated_at = receipt.get("source_updated_at")
            if (not isinstance(title, str) or not title.strip() or len(title) > 1000
                    or not isinstance(excerpt, str) or len(excerpt) > MAX_SOURCE_BODY_CHARS
                    or type(truncated) is not bool
                    or not isinstance(updated_at, str)
                    or parse_time(updated_at) is None
                    or receipt.get("source_title_changed") is not (title != queued.get("title"))
                    or receipt.get("source_updated_at_changed") is not (
                        updated_at != queued.get("updated_at")
                    )):
                raise ValueError("readback current source text and drift flags invalid")
            if not truncated:
                # The complete body fits within the captured excerpt: verify
                # that the reported content hash matches the text being used
                # for source-risk reclassification. Truncated bodies remain
                # explicitly unresolved, never interpreted as risk-free.
                source_hash = hashlib.sha256(json.dumps({
                    "number": int(ISSUE_URL_RE.fullmatch(url).group(3)),
                    "html_url": url,
                    "state": "open" if source_status == "READBACK_OPEN" else "closed",
                    "title": title,
                    "body": excerpt,
                    "updated_at": updated_at,
                }, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode("utf-8")).hexdigest()
                if source_hash != receipt.get("source_content_sha256"):
                    raise ValueError("source text inconsistent with content digest")
        else:
            if (receipt.get("source_title") is not None
                    or receipt.get("source_body_excerpt") is not None
                    or receipt.get("source_body_truncated") is not None):
                raise ValueError("failed readback cannot supply current source text")
        if source_status == "READBACK_OPEN":
            if (receipt.get("source_state") != "open"
                    or not isinstance(receipt.get("source_title_changed"), bool)
                    or not isinstance(receipt.get("source_updated_at_changed"), bool)
                    or not isinstance(receipt.get("source_updated_at"), str)
                    or SHA256_RE.fullmatch(str(receipt.get("source_content_sha256"))) is None):
                raise ValueError("open readback missing valid source snapshot")
            observed_at = parse_time(receipt["readback_at"])
            if observed_at is None:
                raise ValueError("readback timestamp must be timezone-aware")
            current = classify({
                "url": url,
                "title": receipt["source_title"],
                "body_excerpt": receipt["source_body_excerpt"],
                "updated_at": receipt["source_updated_at"],
                "detected_at": receipt["readback_at"],
                "source_state": "open",
            }, observed_at)
            current_policy = current["disposition"]
            current_risks = current["risks"]
            if current_policy in CURRENT_SOURCE_HOLDS:
                decision = current_policy
                next_step = (
                    "Current source excerpt contains a conservative stop/hold "
                    "signal. Reconcile full terms before any further work."
                )
            elif receipt["source_body_truncated"]:
                decision = "RE_TRIAGE_TRUNCATED_SOURCE"
                next_step = (
                    "Read remaining original issue body before any full review; "
                    f"the {MAX_SOURCE_BODY_CHARS}-character excerpt cannot establish absence of risk."
                )
            elif receipt["source_title_changed"] or receipt["source_updated_at_changed"]:
                decision = "RE_TRIAGE_CHANGED_SOURCE"
                next_step = "Reassess updated issue terms against a fresh observation before VERIFY."
            else:
                decision = "REVIEW_OPEN_UNVERIFIED"
                next_step = "Independently verify demand, funding, acceptance and delivery/settlement routes."
        elif source_status == "READBACK_CLOSED":
            if (receipt.get("source_state") != "closed"
                    or SHA256_RE.fullmatch(str(receipt.get("source_content_sha256"))) is None):
                raise ValueError("closed readback missing valid source snapshot")
            decision, next_step = REVIEW_POLICY[source_status]
        elif source_status == "READBACK_FAILED":
            if (receipt.get("source_state") is not None
                    or receipt.get("source_content_sha256") is not None
                    or not isinstance(receipt.get("error_type"), str)
                    or not receipt["error_type"]):
                raise ValueError("failed readback cannot claim observed source state")
            decision, next_step = REVIEW_POLICY[source_status]
        else:
            raise ValueError("invalid readback status")

        decisions.append({
            "queue_rank": rank,
            "url": url,
            "fingerprint": queued["fingerprint"],
            "readback_at": receipt["readback_at"],
            "source_content_sha256": receipt.get("source_content_sha256"),
            "source_body_truncated": receipt.get("source_body_truncated"),
            "current_source_policy": current_policy,
            "current_source_risks": current_risks,
            "readback_status": source_status,
            "review_decision": decision,
            "next_step": next_step,
            "authority": "ADVISORY_ONLY",
            **NO_AUTHORITY,
        })

    if probe.get("selected_queue_ranks") != [r["queue_rank"] for r in receipts]:
        raise ValueError("readback selected ranks do not match receipts")

    counts = dict(sorted(Counter(d["review_decision"] for d in decisions).items()))
    summary = {
        "schema": "value-engine.readback-review/v1",
        "stage": "READBACK_DECISION_PRE_VERIFY",
        "queue_sha256": sha256(queue_data),
        "readbacks_sha256": sha256(receipt_data),
        "probe_summary_sha256": sha256(probe_data),
        "queue_count": len(queue),
        "readback_count": len(receipts),
        "not_read_back_count": len(queue) - len(receipts),
        "review_decisions": counts,
        "selected_queue_ranks": [d["queue_rank"] for d in decisions],
        "authoritative": False,
        **NO_AUTHORITY,
        "note": "Read-only source triage: not funding verification, authorization, settlement or value.",
    }
    return decisions, summary


def run(queue: Path, readbacks: Path, probe_summary: Path,
        output: Path, summary_output: Path) -> dict:
    decisions, summary = review(queue.read_bytes(), readbacks.read_bytes(),
                                probe_summary.read_bytes())
    rendered = "".join(json.dumps(d, ensure_ascii=False, sort_keys=True) + "\n"
                       for d in decisions)
    output.write_text(rendered, encoding="utf-8")
    summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2,
                                         sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--readbacks", type=Path, required=True)
    parser.add_argument("--probe-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.queue, args.readbacks, args.probe_summary,
                         args.output, args.summary), sort_keys=True))


if __name__ == "__main__":
    main()
