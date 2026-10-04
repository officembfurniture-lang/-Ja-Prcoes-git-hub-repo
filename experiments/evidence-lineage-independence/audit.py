#!/usr/bin/env python3
"""Deterministic audit of declared evidence-lineage independence.

This tool never proves truth or independence. It only prevents multiple pieces of
evidence from being counted as independent when their declared lineage contains
a shared potential common cause.
"""

from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

LINEAGE_FIELDS = (
    "source_lineage",
    "model_lineage",
    "data_lineage",
    "prompt_lineage",
    "toolchain_lineage",
)

REQUIRED_FIELDS = ("id", "operator_control", *LINEAGE_FIELDS)


def _norm(value):
    if isinstance(value, list):
        return tuple(sorted(str(x).strip() for x in value if str(x).strip()))
    if value is None:
        return ()
    value = str(value).strip()
    return (value,) if value else ()


def audit(payload):
    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or len(evidence) < 2:
        raise ValueError("at least two evidence records are required")

    missing = []
    normalized = []
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            raise ValueError(f"evidence[{index}] must be an object")
        absent = [field for field in REQUIRED_FIELDS if not _norm(item.get(field))]
        if absent:
            missing.append({"index": index, "id": item.get("id"), "fields": absent})
        normalized.append(
            {
                "id": str(item.get("id", f"evidence-{index}")),
                "operator_control": _norm(item.get("operator_control")),
                **{field: _norm(item.get(field)) for field in LINEAGE_FIELDS},
            }
        )

    pairwise = []
    any_shared = False
    for left, right in combinations(normalized, 2):
        shared = {}
        for field in ("operator_control", *LINEAGE_FIELDS):
            overlap = sorted(set(left[field]) & set(right[field]))
            if overlap:
                shared[field] = overlap
        if shared:
            any_shared = True
        pairwise.append(
            {
                "left": left["id"],
                "right": right["id"],
                "shared_declared_lineage": shared,
            }
        )

    if missing:
        status = "UNRESOLVED"
    elif any_shared:
        status = "CORRELATED_DECLARED_LINEAGE"
    else:
        status = "DISTINCT_DECLARED_LINEAGE"

    return {
        "schema": "horyzont.evidence-lineage-audit/v0.1",
        "status": status,
        "independence_verified": False,
        "note": (
            "DISTINCT_DECLARED_LINEAGE is not proof of independence or truth. "
            "External verification must still test source authenticity, outcome, "
            "and common causes not represented in this declaration."
        ),
        "missing": missing,
        "pairwise": pairwise,
    }


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise SystemExit("usage: audit.py <evidence.json>")
    payload = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    json.dump(audit(payload), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
