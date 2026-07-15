from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA = "horyzont.material-lineage-opportunity-map/v0.1"


def _validate(payload: dict[str, Any]) -> None:
    sources = payload.get("sources")
    demands = payload.get("demands")
    if not isinstance(sources, list) or not sources:
        raise ValueError("at least one material source is required")
    if not isinstance(demands, list) or not demands:
        raise ValueError("at least one material demand is required")
    identifiers: set[str] = set()
    for kind, items in (("source", sources), ("demand", demands)):
        for item in items:
            identifier = str(item.get("id", "")).strip()
            if not identifier or identifier in identifiers:
                raise ValueError("source and demand ids must be non-empty and globally unique")
            identifiers.add(identifier)
            if kind == "source":
                if not item.get("material_code") or float(item.get("mass_kg", 0)) <= 0:
                    raise ValueError(f"source {identifier} requires material_code and positive mass_kg")
            elif not item.get("accepted_material_codes") or float(item.get("min_mass_kg", 0)) <= 0:
                raise ValueError(
                    f"demand {identifier} requires accepted_material_codes and positive min_mass_kg"
                )


def build_opportunity_map(payload: dict[str, Any]) -> dict[str, Any]:
    _validate(payload)
    candidates = []
    matched_sources: set[str] = set()
    matched_demands: set[str] = set()
    for source in payload["sources"]:
        source_tags = set(source.get("quality_tags", []))
        contaminants = set(source.get("contaminants", []))
        for demand in payload["demands"]:
            if source["material_code"] not in set(demand["accepted_material_codes"]):
                continue
            required_tags = set(demand.get("required_tags", []))
            if not required_tags.issubset(source_tags):
                continue
            if contaminants.intersection(demand.get("prohibited_contaminants", [])):
                continue
            if float(source["mass_kg"]) < float(demand["min_mass_kg"]):
                continue
            accepted_regions = set(demand.get("accepted_regions", []))
            region_match = not accepted_regions or source.get("region") in accepted_regions
            tag_score = len(required_tags) / max(len(source_tags), 1)
            mass_ratio = min(1.0, float(source["mass_kg"]) / float(demand["min_mass_kg"]))
            score = round(0.5 * mass_ratio + 0.3 * tag_score + 0.2 * int(region_match), 4)
            candidates.append({
                "source_id": source["id"],
                "demand_id": demand["id"],
                "material_code": source["material_code"],
                "candidate_mass_kg": round(float(source["mass_kg"]), 6),
                "region_match": region_match,
                "required_tags_met": sorted(required_tags),
                "coordination_score": score,
            })
            matched_sources.add(source["id"])
            matched_demands.add(demand["id"])
    candidates.sort(key=lambda item: (-item["coordination_score"], item["source_id"], item["demand_id"]))
    return {
        "schema": SCHEMA,
        "candidate_matches": candidates,
        "unmatched_source_ids": sorted(source["id"] for source in payload["sources"] if source["id"] not in matched_sources),
        "unmatched_demand_ids": sorted(demand["id"] for demand in payload["demands"] if demand["id"] not in matched_demands),
        "candidate_mass_kg": round(sum(item["candidate_mass_kg"] for item in candidates), 6),
        "truth_boundary": {
            "physical_transfer_occurred": False,
            "ownership_transfer_authorized": False,
            "financial_savings_established": False,
            "dpp_compliance_established": False,
            "statement": "Matches are coordination candidates from declared data. Material quality, ownership, logistics and outcomes require external verification.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a bounded material-flow opportunity map")
    parser.add_argument("input", help="Material sources and demands JSON")
    parser.add_argument("--output", help="Optional result JSON path")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rendered = json.dumps(build_opportunity_map(payload), ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
