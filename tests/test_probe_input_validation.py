"""Repository-wide regression tests for public probe input boundaries."""
from __future__ import annotations

import copy
import importlib.util
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p0002 = load_module("repo_probe_p0002", "p0002/src/horyzont/probes/agent_ops_passport.py")
p0003 = load_module("repo_probe_p0003", "src/horyzont/probes/flex_workload.py")
p0004 = load_module("repo_probe_p0004", "p0004/src/horyzont/probes/outcome_mandate.py")
p0005 = load_module("repo_probe_p0005", "p0005/src/horyzont/probes/measurement_compiler.py")
p0006 = load_module("repo_probe_p0006", "p0006/src/horyzont/probes/material_lineage.py")
p0007 = load_module("repo_probe_p0007", "p0007/src/horyzont/probes/early_action_simulator.py")


def valid_workload():
    return {
        "input_kind": "synthetic_test",
        "slot_minutes": 30,
        "site_capacity_kw": 20,
        "grid_stress": [0.9, 0.2, 0.3, 0.4],
        "tasks": [
            {
                "id": "a",
                "power_kw": 5,
                "duration_slots": 1,
                "earliest_slot": 0,
                "latest_end_slot": 4,
                "deferrable": True,
                "priority": 50,
            }
        ],
    }


def valid_mandate():
    return {
        "issuer": "test",
        "task": "freeze only",
        "authority": "A1",
        "budget": {"amount": 0, "currency": "TEST"},
        "criteria": [{"metric": "ok", "operator": "==", "target": True}],
        "evidence_policy": {"allowed_schemes": ["https"]},
        "kill_gate": "stop",
        "expires_at": "2099-01-01T00:00:00Z",
    }


def valid_measurement():
    return {
        "id": "MP-TEST",
        "question": "Does the bounded fixture pass?",
        "hypothesis": "The fixture passes validation.",
        "anomaly": {"metric": "gap_rate", "observed": 0.5},
        "variables": [
            {"name": "enabled", "role": "independent", "unit": "boolean"},
            {"name": "gap_rate", "role": "dependent", "unit": "ratio"},
        ],
        "measurement": {
            "source_ref": "dataset://fixture/v1",
            "sample_count": 2,
            "sampling_unit": "record",
            "comparison": "same fixture",
        },
        "decision_rule": {"metric": "gap_rate", "operator": "<=", "threshold": 0.4},
        "hazard": {
            "involves_people": False,
            "involves_living_systems": False,
            "involves_hazardous_materials": False,
            "involves_critical_infrastructure": False,
        },
        "authority": "A1",
        "expires_at": "2099-01-01T00:00:00Z",
    }


def valid_lineage():
    return {
        "sources": [
            {
                "id": "S1",
                "material_code": "WOOD",
                "mass_kg": 10,
                "quality_tags": ["dry"],
                "contaminants": [],
                "region": "x",
            }
        ],
        "demands": [
            {
                "id": "D1",
                "accepted_material_codes": ["WOOD"],
                "required_tags": ["dry"],
                "prohibited_contaminants": [],
                "min_mass_kg": 5,
                "accepted_regions": ["x"],
            }
        ],
    }


def valid_backtest():
    return {
        "policy": {
            "warning_threshold": 0.7,
            "minimum_lead_hours": 1,
            "action_cost": 1,
        },
        "episodes": [
            {
                "id": "E1",
                "warning_score": 0.8,
                "lead_hours": 2,
                "event_occurred": True,
                "baseline_loss_units": 10,
                "mitigated_loss_units": 3,
            },
            {
                "id": "E2",
                "warning_score": 0.2,
                "lead_hours": 2,
                "event_occurred": False,
                "baseline_loss_units": 0,
                "mitigated_loss_units": 0,
            },
        ],
    }


class ProbeBoundaryTests(unittest.TestCase):
    def test_positive_smoke_paths_remain_available(self):
        self.assertFalse(p0003.analyze_workload(valid_workload())["truth_boundary"]["physical_savings_claimed"])
        self.assertFalse(p0004.freeze_mandate(valid_mandate())["truth_boundary"]["payment_authorized"])
        self.assertFalse(p0005.compile_protocol(valid_measurement())["truth_boundary"]["experiment_executed"])
        self.assertFalse(p0006.build_opportunity_map(valid_lineage())["truth_boundary"]["physical_transfer_occurred"])
        self.assertFalse(p0007.simulate(valid_backtest())["truth_boundary"]["real_action_taken"])

    def test_p0002_does_not_follow_symlinks_outside_scan_root(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        with tempfile.TemporaryDirectory() as root_dir, tempfile.TemporaryDirectory() as outside_dir:
            root = Path(root_dir)
            outside = Path(outside_dir) / "outside.py"
            outside.write_text("SECRET = 'outside'\n", encoding="utf-8")
            link = root / "linked-outside.py"
            try:
                link.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlink unavailable: {exc}")
            (root / "inside.py").write_text("VALUE = 1\n", encoding="utf-8")
            passport = p0002.build_passport(root, generated_at="2026-01-01T00:00:00Z")
            paths = {entry["path"] for entry in passport["inventory"]}
            self.assertIn("inside.py", paths)
            self.assertNotIn("linked-outside.py", paths)

    def test_p0003_rejects_boolean_string_and_nonfinite_coercions(self):
        case = valid_workload()
        case["tasks"][0]["deferrable"] = "false"
        with self.assertRaises(ValueError):
            p0003.analyze_workload(case)

        case = valid_workload()
        case["tasks"][0]["duration_slots"] = 1.5
        with self.assertRaises(ValueError):
            p0003.analyze_workload(case)

        case = valid_workload()
        case["site_capacity_kw"] = float("nan")
        with self.assertRaises(ValueError):
            p0003.analyze_workload(case)

    def test_p0004_rejects_naive_time_and_nonfinite_budget(self):
        case = valid_mandate()
        case["expires_at"] = "2099-01-01T00:00:00"
        with self.assertRaises(ValueError):
            p0004.validate_draft(case)

        case = valid_mandate()
        case["budget"]["amount"] = float("nan")
        with self.assertRaises(ValueError):
            p0004.validate_draft(case)

    def test_p0005_rejects_fractional_count_nonfinite_and_string_hazard(self):
        case = valid_measurement()
        case["measurement"]["sample_count"] = 2.5
        with self.assertRaises(ValueError):
            p0005.validate_draft(case)

        case = valid_measurement()
        case["decision_rule"]["threshold"] = float("inf")
        with self.assertRaises(ValueError):
            p0005.validate_draft(case)

        case = valid_measurement()
        case["hazard"]["involves_people"] = "false"
        with self.assertRaises(ValueError):
            p0005.validate_draft(case)

    def test_p0006_rejects_nonfinite_mass_and_bad_code_list(self):
        case = valid_lineage()
        case["sources"][0]["mass_kg"] = float("nan")
        with self.assertRaises(ValueError):
            p0006.build_opportunity_map(case)

        case = valid_lineage()
        case["demands"][0]["accepted_material_codes"] = ["WOOD", 7]
        with self.assertRaises(ValueError):
            p0006.build_opportunity_map(case)

    def test_p0006_uses_regions_as_eligibility_and_does_not_double_count_source_mass(self):
        case = valid_lineage()
        case["demands"].append({
            "id": "D2",
            "accepted_material_codes": ["WOOD"],
            "required_tags": ["dry"],
            "prohibited_contaminants": [],
            "min_mass_kg": 5,
            "accepted_regions": ["x"],
        })
        result = p0006.build_opportunity_map(case)
        self.assertEqual(len(result["candidate_matches"]), 2)
        self.assertEqual(result["candidate_mass_kg"], 10)
        self.assertEqual(result["candidate_pair_mass_kg"], 20)

        outside = valid_lineage()
        outside["sources"][0]["region"] = "y"
        result = p0006.build_opportunity_map(outside)
        self.assertEqual(result["candidate_matches"], [])
        self.assertEqual(result["candidate_mass_kg"], 0)

    def test_p0007_rejects_string_boolean_and_nonfinite_values(self):
        case = valid_backtest()
        case["episodes"][0]["event_occurred"] = "false"
        with self.assertRaises(ValueError):
            p0007.simulate(case)

        case = valid_backtest()
        case["episodes"][0]["warning_score"] = float("nan")
        with self.assertRaises(ValueError):
            p0007.simulate(case)


if __name__ == "__main__":
    unittest.main()
