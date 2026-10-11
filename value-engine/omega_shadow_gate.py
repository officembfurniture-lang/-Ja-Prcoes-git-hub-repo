#!/usr/bin/env python3
"""Issue #2: open the read-only Ω testing lane without promoting the driver.

This is a compatibility/safety paired check on real sensor data. It is NOT
an effectiveness trial: no measured human burden or verified material effect.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from triage import classify, newest_by_url

MAX_PAIRS = 16
PINNED_OMEGA_SHA = "23019008e67b897a008ff786badf3aa976da84a5"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_rows(raw: bytes) -> list[dict]:
    try:
        text = raw.decode("utf-8")
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("sensor observation file is malformed") from exc
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("observation records must be objects")
    return rows


def driver_at(path: Path):
    if not path.is_file():
        raise ValueError("pinned Omega driver file unavailable")
    spec = importlib.util.spec_from_file_location("omega_shadow_pinned", path)
    if spec is None or spec.loader is None:
        raise ValueError("pinned Omega driver could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if not callable(getattr(module, "evaluate", None)):
        raise ValueError("pinned Omega driver has no evaluator")
    return module.evaluate


def trial(state: dict, observation_bytes: bytes, evaluator,
          source_revision: str, *, limit: int = MAX_PAIRS) -> dict:
    """Same real inputs; baseline and candidate both forbidden to promote.

    A non-authoritative observed source is never upgraded to 'VERIFIED'.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_PAIRS:
        raise ValueError("invalid trial sample limit")
    if not isinstance(state, dict) or state.get("engine") != "VALUE_ENGINE_v2":
        raise ValueError("unexpected sensor state")
    last = state.get("last_cycle_result")
    if (not isinstance(last, dict)
            or last.get("observations_sha256") != digest(observation_bytes)
            or not isinstance(last.get("cycle_id"), str)):
        raise ValueError("observation bytes do not match sensor state readback")
    stamp = last.get("at")
    if not isinstance(stamp, str):
        raise ValueError("sensor cycle has no timestamp")
    instant = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("sensor timestamp is not timezone aware")
    now = instant.astimezone(timezone.utc)
    all_rows = read_rows(observation_bytes)
    latest = newest_by_url(all_rows)
    # Freeze sample based on source identity *before* comparing decisions.
    ranked = sorted(
        (row for row in latest if isinstance(row.get("url"), str)
         and row.get("status") == "OBSERVED"
         and row.get("primary_source_verified") is False
         and row.get("demand_or_reward_verified") is False
         and type(row.get("realized_value")) is int
         and row.get("realized_value") == 0),
        key=lambda row: (digest(row["url"].encode("utf-8")), row["url"]),
    )
    cases = []
    for item in ranked[:limit]:
        original = classify(item, now)
        baseline = original["disposition"]
        observed_input = {
            "previous_state": {"disposition": baseline, "source_url": item["url"]},
            "candidate_state": {"disposition": baseline, "source_url": item["url"]},
            # Keep real sensor observations OBSERVED, never relabel VERIFIED.
            "evidence": [{"id": "source_observed", "status": "OBSERVED",
                          "already_known": False}],
            "predictions": [],
            "action": {},
            "decision_effect": {},
            "debts": {},
            "human_burden": {"measured": False},
        }
        verdict = evaluator(observed_input)
        if verdict.verdict == "PROMOTE":
            raise ValueError("Omega promoted observation-only data without evidence")
        if verdict.action_verified or verdict.material_effect_verified:
            raise ValueError("Omega claimed verified action/effect on raw observation")
        cases.append({
            "source_url_sha256": digest(item["url"].encode("utf-8")),
            "baseline_disposition": baseline,
            "baseline_permission_to_produce": False,
            "omega_verdict": verdict.verdict,
            "omega_evidence_delta": verdict.evidence_delta,
            "omega_action_verified": verdict.action_verified,
            "omega_material_effect_verified": verdict.material_effect_verified,
            "human_burden_measured": False,
            "promoted": False,
        })
    if not cases:
        raise ValueError("no valid real observations to compare")
    counts = dict(sorted(Counter(x["omega_verdict"] for x in cases).items()))
    return {
        "schema": "omega.shadow-paired-safety-gate/v1",
        "phase": "EXPERIMENT_OPEN_PROMOTION_HOLD",
        "origin": "persisted real VALUE_ENGINE observations",
        "sensor_cycle_id": last["cycle_id"],
        "source_revision": source_revision,
        "observations_sha256": digest(observation_bytes),
        "omega_candidate_revision": PINNED_OMEGA_SHA,
        "frozen_sample_rule": "ascending SHA256(url), unique newest source revision",
        "sample_size": len(cases),
        "same_input_for_baseline_and_candidate": True,
        "baseline_permission_to_produce": False,
        "omega_verdict_counts": counts,
        "omega_promotions": 0,
        "observed_material_improvements": 0,
        "human_correction_burden_measured": False,
        "external_result_verified": False,
        "promotion_gate": "HOLD",
        "next_discriminating_test": (
            "Pair future genuinely decision-changing cases with independently "
            "verified actions/effects and measured human correction/restoration "
            "burden, without outcome-driven retuning."
        ),
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--omega-driver", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_revision = args.source_revision
    if len(source_revision) != 40 or any(c not in "0123456789abcdef" for c in source_revision):
        parser.error("--source-revision must be an exact 40-char lowercase git SHA")
    result = trial(
        json.loads(args.state.read_text(encoding="utf-8")),
        args.observations.read_bytes(), driver_at(args.omega_driver),
        source_revision,
    )
    args.output.write_text(json.dumps(result, sort_keys=True, ensure_ascii=False,
                                      indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "cases"},
                     sort_keys=True))


if __name__ == "__main__":
    main()
