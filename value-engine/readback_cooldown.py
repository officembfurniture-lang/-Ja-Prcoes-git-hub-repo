"""Read-only, bounded cross-run feedback from a previous trusted triage artifact.

Prior observations only control *when to recheck*, never economic authorization.
An invalid/unavailable artifact cannot suppress a current source readback.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cycle import ISSUE_URL_RE

MAX_GETS = 3
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
COOLDOWNS = {
    "READBACK_OPEN": timedelta(hours=2),
    "READBACK_CLOSED": timedelta(hours=6),
    "READBACK_FAILED": timedelta(hours=2),
}
# Stable 404/410 locators are rechecked on the six-day snapshot cadence. This
# avoids burning every short-cycle GET slot on a missing locator while allowing
# a changed fingerprint (newly discovered/revised source) to bypass suppression.
NOT_FOUND_COOLDOWN = timedelta(days=6)
# A full 24k-bounded capture that still truncates cannot be fully re-triaged.
# Do not let the same unchanged long body consume one of the three live GET
# slots every short cycle; still recheck on the ordinary snapshot cadence.
TRUNCATED_SOURCE_COOLDOWN = timedelta(days=6)
NO_AUTHORITY_FIELDS = (
    "primary_source_verified", "demand_or_reward_verified",
    "settlement_route_verified", "authorization_to_execute",
)


def load_ndjson(path: Path) -> list[dict]:
    output = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError("prior artifact row not an object")
            output.append(item)
    return output


def parsed_utc(value) -> datetime:
    if not isinstance(value, str):
        raise ValueError("prior timestamp missing")
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("prior timestamp must include timezone")
    return instant.astimezone(timezone.utc)


def recent_readback_suppressions(bundle: Path, at: datetime,
                                 current: list[tuple[int, dict]]) -> dict[str, str]:
    """Validate the prior *whole* queue+receipt binding before using any hint.

    Only an unchanged queue fingerprint and same GitHub URL can be temporarily
    deprioritized. The result is a retry hint, never 'source still closed'.
    """
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("current clock must be timezone aware")
    queue_path = bundle / "value-engine-triage-queue.ndjson"
    receipts_path = bundle / "value-engine-source-readback.ndjson"
    summary_path = bundle / "value-engine-source-readback-summary.json"
    queue_bytes = queue_path.read_bytes()
    prior_queue = load_ndjson(queue_path)
    prior_receipts = load_ndjson(receipts_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if (not isinstance(summary, dict)
            or summary.get("schema") != "value-engine.source-readback/v2"
            or summary.get("stage") != "SOURCE_READBACK_NON_AUTHORITATIVE"
            or summary.get("authoritative") is not False
            or summary.get("queue_sha256") != hashlib.sha256(queue_bytes).hexdigest()
            or type(summary.get("queue_count")) is not int
            or summary["queue_count"] != len(prior_queue)
            or type(summary.get("results")) is not int
            or summary["results"] != len(prior_receipts)
            or type(summary.get("attempted")) is not int
            or summary["attempted"] != len(prior_receipts)
            or len(prior_receipts) > MAX_GETS
            or summary.get("selected_queue_ranks")
               != [row.get("queue_rank") for row in prior_receipts]):
        raise ValueError("prior source probe does not bind its queue and receipts")
    for k in NO_AUTHORITY_FIELDS:
        if summary.get(k) is not False:
            raise ValueError("prior source probe cannot grant authority")
    if type(summary.get("realized_value")) is not int or summary["realized_value"] != 0:
        raise ValueError("prior source probe realized value is invalid")

    readback_at = parsed_utc(summary.get("readback_at"))
    elapsed = at.astimezone(timezone.utc) - readback_at
    if elapsed < timedelta(0):
        raise ValueError("prior readback is from the future")
    prior_allowed = {}
    ranks_seen = set()
    for receipt in prior_receipts:
        rank = receipt.get("queue_rank")
        if type(rank) is not int or not 1 <= rank <= len(prior_queue) or rank in ranks_seen:
            raise ValueError("prior receipt rank invalid or duplicated")
        ranks_seen.add(rank)
        source = prior_queue[rank - 1]
        url = source.get("url")
        if (not isinstance(url, str) or ISSUE_URL_RE.fullmatch(url) is None
                or source.get("disposition") != "QUEUE_VERIFY"
                or source.get("status") != "OBSERVED"
                or receipt.get("queue_source_url") != url
                or receipt.get("queue_fingerprint") != source.get("fingerprint")
                or receipt.get("queue_title") != source.get("title")
                or receipt.get("queue_source_updated_at") != source.get("updated_at")
                or receipt.get("readback_at") != summary["readback_at"]):
            raise ValueError("prior readback receipt does not match its queue")
        for k in NO_AUTHORITY_FIELDS:
            if receipt.get(k) is not False:
                raise ValueError("prior readback receipt cannot grant authority")
        if type(receipt.get("realized_value")) is not int or receipt["realized_value"] != 0:
            raise ValueError("prior readback receipt has nonzero/invalid value")
        status = receipt.get("status")
        http_status = None
        source_revision_changed = False
        source_body_truncated = False
        if status == "READBACK_OPEN":
            if receipt.get("source_state") != "open":
                raise ValueError("prior open status inconsistent")
            if (type(receipt.get("source_body_truncated")) is not bool
                    or type(receipt.get("source_title_changed")) is not bool
                    or type(receipt.get("source_updated_at_changed")) is not bool):
                raise ValueError("prior open readback drift/truncation flags invalid")
            source_body_truncated = receipt["source_body_truncated"]
            source_revision_changed = (
                receipt["source_title_changed"]
                or receipt["source_updated_at_changed"]
            )
        elif status == "READBACK_CLOSED":
            if receipt.get("source_state") != "closed":
                raise ValueError("prior closed status inconsistent")
            if (type(receipt.get("source_body_truncated")) is not bool
                    or type(receipt.get("source_title_changed")) is not bool
                    or type(receipt.get("source_updated_at_changed")) is not bool):
                raise ValueError("prior closed readback drift/truncation flags invalid")
            source_body_truncated = receipt["source_body_truncated"]
            source_revision_changed = (
                receipt["source_title_changed"]
                or receipt["source_updated_at_changed"]
            )
        elif status == "READBACK_FAILED":
            if (receipt.get("source_state") is not None
                    or receipt.get("source_content_sha256") is not None):
                raise ValueError("failed prior readback pretends to prove source state")
            http_status = receipt.get("http_error_status")
            if http_status not in (403, 404, 410):
                continue
        else:
            raise ValueError("unsupported prior readback status")
        # A changed source must return to the sensor so its revised snapshot
        # can enter the canonical observation archive. Never suppress it only
        # because the URL or queued fingerprint is unchanged.
        if source_revision_changed:
            continue

        # This is not permission to claim source-state truth at the new clock.
        # A 404/410 is about the locator, not the task's semantic closure.
        # An unchanged truncated source also receives the six-day snapshot TTL:
        # the current bounded excerpt cannot resolve its remaining tail, and a
        # fresh copy of the same excerpt adds no evidence.
        if status == "READBACK_FAILED" and http_status in (404, 410):
            cooldown = NOT_FOUND_COOLDOWN
        elif source_body_truncated:
            cooldown = TRUNCATED_SOURCE_COOLDOWN
        else:
            cooldown = COOLDOWNS[status]
        if elapsed < cooldown:
            prior_allowed[url] = (source.get("fingerprint"), status)

    current_identity = {row.get("url"): row.get("fingerprint") for _, row in current}
    return {
        url: status for url, (fingerprint, status) in prior_allowed.items()
        if isinstance(fingerprint, str) and fingerprint
        and current_identity.get(url) == fingerprint
    }
