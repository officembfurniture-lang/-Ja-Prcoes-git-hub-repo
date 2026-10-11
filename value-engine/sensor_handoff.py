#!/usr/bin/env python3
"""Bind workflow_run triage to the exact persisted VALUE_ENGINE sensor cycle.

Read-only Git history inspection. A successful workflow_run event alone does
not show that checkout contains the triggering sensor's persisted data.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

STATE_PATH = "value-engine/state.json"
LEDGER_PATH = "value-engine/run-ledger.ndjson"
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")


def git_text(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=root, text=True, stderr=subprocess.PIPE
    )


def last_ledger_record(text: str) -> dict:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("sensor ledger contains no records")
    record = json.loads(lines[-1])
    if not isinstance(record, dict):
        raise ValueError("last sensor ledger row must be a JSON object")
    return record


def matches_sensor(state: dict, ledger: dict, run_id: int) -> bool:
    """Exact run ID, state/ledger provenance and result counts must agree."""
    if type(run_id) is not int or run_id <= 0:
        return False
    if not isinstance(state, dict) or not isinstance(ledger, dict):
        return False
    cycle = state.get("cycle")
    if type(cycle) is not int or cycle <= 0:
        return False
    expected = f"cycle-{cycle}-{run_id}"
    result = state.get("last_cycle_result")
    if not isinstance(result, dict):
        return False
    if (result.get("cycle_id") != expected or ledger.get("cycle_id") != expected
            or ledger.get("result") != "SENSE_COMPLETE"
            or state.get("phase") != "IDLE"
            or result.get("at") != ledger.get("at")
            or result.get("source_errors") != ledger.get("errors")):
        return False
    for field in ("new_observations", "refreshed_snapshots",
                  "direct_readback_attempts", "direct_readback_captures",
                  "direct_readback_closed"):
        a, b = result.get(field, 0), ledger.get(field, 0)
        if type(a) is not int or type(b) is not int or a < 0 or b < 0 or a != b:
            return False
    if (result.get("selected") != 0 or result.get("delivered") != 0
            or result.get("paid") != 0 or ledger.get("realized_value") != 0):
        return False
    # Later cycles include a full-byte archive checksum. Do not allow the two
    # authoritative in-repository receipts to disagree about that input.
    state_digest = result.get("observations_sha256")
    ledger_digest = ledger.get("observations_sha256")
    if state_digest is not None or ledger_digest is not None:
        if (not isinstance(state_digest, str)
                or len(state_digest) != 64
                or any(ch not in "0123456789abcdef" for ch in state_digest)
                or state_digest != ledger_digest):
            return False
    return True


def locate_sensor_commit(root: Path, run_id: int, max_commits: int = 256) -> str:
    if type(run_id) is not int or run_id <= 0:
        raise ValueError("sensor run ID must be positive integer")
    history = git_text(root, "rev-list", f"--max-count={max_commits}",
                       "origin/main", "--", STATE_PATH).splitlines()
    for sha in history:
        if not COMMIT_RE.fullmatch(sha):
            raise ValueError("unexpected commit hash from git history")
        try:
            state = json.loads(git_text(root, "show", f"{sha}:{STATE_PATH}"))
        except (json.JSONDecodeError, subprocess.CalledProcessError):
            continue
        if (not isinstance(state, dict)
                or not isinstance(state.get("last_cycle_result"), dict)
                or not str(state["last_cycle_result"].get("cycle_id", "")).endswith(
                    f"-{run_id}")):
            continue
        try:
            ledger = last_ledger_record(git_text(root, "show", f"{sha}:{LEDGER_PATH}"))
        except (json.JSONDecodeError, subprocess.CalledProcessError, ValueError) as exc:
            raise ValueError("sensor run found but ledger unavailable or corrupt") from exc
        if not matches_sensor(state, ledger, run_id):
            raise ValueError("sensor state and ledger mismatch; stop triage")
        return sha
    raise ValueError(
        "no safely matched persisted sensor commit within bounded main history"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path,
                        help="GitHub Actions GITHUB_OUTPUT file (not repository state)")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sha = locate_sensor_commit(root, args.run_id)
    with args.output.open("a", encoding="utf-8") as handle:
        handle.write(f"state_commit={sha}\n")
    print(json.dumps({
        "stage": "EXACT_SENSOR_HANDOFF",
        "source_run_id": args.run_id,
        "persisted_state_commit": sha,
        "authoritative": False,
        "note": "Proves sensor-state/ledger identity, not economic or external verification.",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
