#!/usr/bin/env python3
"""Bounded, read-only primary-source readback evidence for a pre-VERIFY queue.

A successful GitHub GET establishes a source readback, NOT escrow, funding,
buyer intent, approval to work, successful delivery or realized value.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.error
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from cycle import ISSUE_URL_RE, github_issue_readback

MAX_ISSUES = 3
NO_AUTHORITY = {
    "primary_source_verified": False,
    "demand_or_reward_verified": False,
    "settlement_route_verified": False,
    "authorization_to_execute": False,
    "realized_value": 0,
}


def utc_iso(at: datetime) -> str:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("readback timestamp must be timezone-aware")
    return at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_hash(value: dict) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def load_queue(path: Path) -> list[dict]:
    result = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid queue JSON at line {n}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"invalid queue record at line {n}")
        result.append(row)
    return result


def probe(queue: Path, output: Path, summary: Path, *,
          limit: int = MAX_ISSUES, at: datetime | None = None,
          fetcher: Callable[[str, str | None], dict] = github_issue_readback,
          token: str | None = None) -> dict:
    if not (1 <= limit <= MAX_ISSUES):
        raise ValueError("probe limit must be 1..3")
    observed_at = utc_iso(at or datetime.now(timezone.utc))
    raw_hash = hashlib.sha256(queue.read_bytes()).hexdigest()
    rows = load_queue(queue)
    receipts: list[dict] = []
    attempted_urls: set[str] = set()
    attempts = 0

    for row in rows:
        if attempts >= limit:
            break
        url = row.get("url")
        # Never fetch an arbitrary URL or promote a caller-asserted VERIFIED row.
        if (row.get("disposition") != "QUEUE_VERIFY"
                or row.get("status") != "OBSERVED"
                or row.get("primary_source_verified") is not False
                or row.get("demand_or_reward_verified") is not False
                or row.get("realized_value") != 0
                or not isinstance(url, str)
                or ISSUE_URL_RE.fullmatch(url) is None):
            continue
        if url in attempted_urls:
            continue
        attempted_urls.add(url)
        attempts += 1
        match = ISSUE_URL_RE.fullmatch(url)
        assert match is not None
        expected_number = int(match.group(3))
        receipt = {
            "queue_source_url": url,
            "queue_source_updated_at": row.get("updated_at"),
            "queue_title": row.get("title"),
            "queue_fingerprint": row.get("fingerprint"),
            "readback_at": observed_at,
            "status": "READBACK_FAILED",
            "source_state": None,
            "source_updated_at": None,
            "source_content_sha256": None,
            "source_title_changed": None,
            "source_updated_at_changed": None,
            "comment_count": None,
            "http_error_status": None,
            "error_type": None,
            **NO_AUTHORITY,
        }
        try:
            issue = fetcher(url, token)
            if not isinstance(issue, dict):
                raise ValueError("invalid_issue_payload")
            if (issue.get("html_url") != url
                    or issue.get("number") != expected_number
                    or issue.get("state") not in ("open", "closed")
                    or "pull_request" in issue
                    or not isinstance(issue.get("title"), str)
                    or not isinstance(issue.get("body"), (str, type(None)))
                    or not isinstance(issue.get("updated_at"), str)):
                raise ValueError("source_identity_or_shape_mismatch")
            source_fields = {
                "number": issue["number"],
                "html_url": issue["html_url"],
                "state": issue["state"],
                "title": issue["title"],
                "body": issue.get("body") or "",
                "updated_at": issue["updated_at"],
            }
            receipt.update({
                "status": "READBACK_OPEN" if issue["state"] == "open"
                          else "READBACK_CLOSED",
                "source_state": issue["state"],
                "source_updated_at": issue["updated_at"],
                "source_content_sha256": canonical_hash(source_fields),
                "source_title_changed": issue["title"] != row.get("title"),
                "source_updated_at_changed": issue["updated_at"] != row.get("updated_at"),
                "comment_count": issue.get("comments") if isinstance(issue.get("comments"), int) else None,
            })
        except Exception as exc:
            receipt["error_type"] = type(exc).__name__
            if isinstance(exc, urllib.error.HTTPError):
                receipt["http_error_status"] = exc.code
        receipts.append(receipt)

    output.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                for r in receipts), encoding="utf-8",
    )
    disposition_counts = dict(sorted(Counter(r["status"] for r in receipts).items()))
    report = {
        "schema": "value-engine.source-readback/v1",
        "stage": "SOURCE_READBACK_NON_AUTHORITATIVE",
        "queue_sha256": raw_hash,
        "readback_at": observed_at,
        "limit": limit,
        "queue_count": len(rows),
        "attempted": attempts,
        "results": len(receipts),
        "dispositions": disposition_counts,
        "authoritative": False,
        **NO_AUTHORITY,
        "note": "Independent GET confirms source fields only; funding, eligibility, routes, "
                "execution, outcomes and payments remain unverified.",
    }
    summary.write_text(json.dumps(report, indent=2, ensure_ascii=False,
                                  sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=MAX_ISSUES)
    args = parser.parse_args()
    result = probe(args.queue, args.output, args.summary, limit=args.limit,
                   token=os.environ.get("GITHUB_TOKEN"))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
