"""Repository-wide regression tests for public probe input boundaries."""
from __future__ import annotations

import copy
import importlib.util
import hashlib
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
    def test_attestation_rejects_rehashed_invalid_mandates(self):
        for field, value in (("criteria", []), ("schema", "unsupported"),
                             ("authority", []), ("evidence_policy", None)):
            with self.subTest(field=field):
                mandate = p0004.freeze_mandate(valid_mandate())
                mandate[field] = value
                mandate.pop("mandate_hash")
                mandate["mandate_hash"] = hashlib.sha256(
                    p0004.canonical_json(mandate).encode()).hexdigest()
                attestation = {"mandate_hash": mandate["mandate_hash"],
                               "observed_at": "2026-10-12T00:00:00Z",
                               "metrics": {"ok": True},
                               "evidence_refs": ["https://example.org/evidence"]}
                with self.assertRaises(ValueError):
                    p0004.evaluate_attestation(mandate, attestation)

    def test_attestation_rejects_nonobject_metrics(self):
        mandate = p0004.freeze_mandate(valid_mandate())
        for metrics in (None, [], "ok", 1):
            with self.subTest(metrics=metrics):
                with self.assertRaises(ValueError):
                    p0004.evaluate_attestation(mandate, {
                        "observed_at": "2026-10-12T00:00:00Z", "metrics": metrics})

    def test_mandate_requires_string_criterion_identity(self):
        for field, value in (("metric", None), ("metric", 1),
                             ("metric", " ok "), ("operator", [])):
            draft = valid_mandate()
            draft["criteria"][0][field] = value
            with self.assertRaises(ValueError):
                p0004.freeze_mandate(draft)

    def test_measurement_rejects_malformed_nested_contracts(self):
        for field in ("anomaly", "measurement", "decision_rule"):
            for value in (None, [], "invalid", 7):
                with self.subTest(field=field, value=value):
                    draft = valid_measurement()
                    draft[field] = value
                    with self.assertRaises(ValueError):
                        p0005.compile_protocol(draft)
        for value in (None, [], "invalid", 7):
            draft = valid_measurement()
            draft["variables"][0] = value
            with self.assertRaises(ValueError):
                p0005.compile_protocol(draft)

    def test_measurement_rejects_nontext_identifiers_and_operators(self):
        for section, field in (("anomaly", "metric"), ("decision_rule", "metric"),
                               ("decision_rule", "operator"), ("variable", "name"),
                               ("variable", "role")):
            for value in (None, [], {}, 7, True, " "):
                with self.subTest(section=section, field=field, value=value):
                    draft = valid_measurement()
                    target = draft["variables"][0] if section == "variable" else draft[section]
                    target[field] = value
                    with self.assertRaises(ValueError):
                        p0005.compile_protocol(draft)

    def test_measurement_rejects_whitespace_variable_identity(self):
        draft = valid_measurement()
        draft["variables"][1]["name"] = " gap_rate "
        with self.assertRaises(ValueError):
            p0005.compile_protocol(draft)

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

    def test_p0003_rejects_higher_total_stress_from_greedy_optimization(self):
        # Without a dominance check, the local heuristic picks a cheap slot for
        # a 1 kW task, displacing a mandatory 2 kW task to an expensive slot.
        workload = {
            "slot_minutes": 30,
            "site_capacity_kw": 2,
            "grid_stress": [2, 1, 5],
            "tasks": [
                {"id": "small", "power_kw": 1, "duration_slots": 1,
                 "earliest_slot": 0, "latest_end_slot": 3, "deferrable": True,
                 "priority": 1},
                {"id": "large", "power_kw": 2, "duration_slots": 1,
                 "earliest_slot": 1, "latest_end_slot": 3, "deferrable": True,
                 "priority": 0},
            ],
        }
        report = p0003.analyze_workload(workload)
        self.assertEqual(report["baseline"]["weighted_grid_stress"], 2)
        self.assertEqual(report["grid_aware"]["weighted_grid_stress"], 2)
        self.assertEqual(report["grid_aware"]["task_start_slots"],
                         report["baseline"]["task_start_slots"])
        self.assertEqual(report["planned_shifted_energy_kwh"], 0)
        self.assertEqual(report["moved_task_ids"], [])
        self.assertEqual(report["optimization_selection"],
                         "baseline_fallback_higher_stress")
        self.assertFalse(report["truth_boundary"]["physical_savings_claimed"])

    def test_p0003_falls_back_to_feasible_baseline_on_greedy_dead_end(self):
        workload = {
            "slot_minutes": 30,
            "site_capacity_kw": 1,
            "grid_stress": [5, 5, 4],
            "tasks": [
                {"id": "must-use-last-slot", "power_kw": 1, "duration_slots": 1,
                 "earliest_slot": 2, "latest_end_slot": 3, "deferrable": True,
                 "priority": 1},
                {"id": "flex", "power_kw": 1, "duration_slots": 1,
                 "earliest_slot": 0, "latest_end_slot": 3, "deferrable": True,
                 "priority": 2},
            ],
        }
        report = p0003.analyze_workload(workload)
        self.assertEqual(report["baseline"]["task_start_slots"],
                         {"flex": 0, "must-use-last-slot": 2})
        self.assertEqual(report["baseline"]["weighted_grid_stress"], 4.5)
        self.assertEqual(report["grid_aware"]["task_start_slots"],
                         report["baseline"]["task_start_slots"])
        self.assertEqual(report["optimization_selection"],
                         "baseline_fallback_heuristic_infeasible")
        self.assertEqual(report["planned_shifted_energy_kwh"], 0)

    def test_p0003_still_selects_successful_grid_aware_plan(self):
        report = p0003.analyze_workload(valid_workload())
        self.assertEqual(report["optimization_selection"], "grid_aware_heuristic")
        self.assertEqual(report["moved_task_ids"], ["a"])
        self.assertLess(report["grid_aware"]["weighted_grid_stress"],
                        report["baseline"]["weighted_grid_stress"])

    def test_p0003_rejects_overflowing_weighted_objective(self):
        workload = valid_workload()
        workload["site_capacity_kw"] = 1e308
        workload["tasks"][0]["power_kw"] = 1e308
        workload["grid_stress"] = [1e308] * 4
        with self.assertRaisesRegex(ValueError, "weighted grid stress"):
            p0003.analyze_workload(workload)

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

    def test_p0004_rejects_unaddressable_evidence_and_boolean_numeric_equivalence(self):
        mandate = p0004.freeze_mandate(valid_mandate())
        attestation = {
            "mandate_hash": mandate["mandate_hash"],
            "observed_at": "2026-10-11T08:00:00Z",
            "metrics": {"ok": True},
            "evidence_refs": ["https://example.org/real-address"],
        }
        self.assertTrue(p0004.evaluate_attestation(mandate, attestation)["accepted"])
        for forged in ("https:made-up", "https:///no-host", "https://alice:secret@example.com",
                       "https://[unclosed", "https://example.org/not real"):
            with self.subTest(reference=forged):
                other = copy.deepcopy(attestation)
                other["evidence_refs"] = [forged]
                result = p0004.evaluate_attestation(mandate, other)
                self.assertFalse(result["accepted"])
                self.assertFalse(result["checks"]["external_evidence_references_valid"])
        another = copy.deepcopy(attestation)
        another["metrics"] = {"ok": 1}
        verdict = p0004.evaluate_attestation(mandate, another)
        self.assertFalse(verdict["accepted"])
        self.assertFalse(verdict["checks"]["all_criteria_passed"])

    def test_p0004_rejects_invalid_policy_shapes_and_text_fields(self):
        for field in ("issuer", "task", "kill_gate"):
            case = valid_mandate()
            case[field] = None
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    p0004.validate_draft(case)
        for policy in ("https", {"allowed_schemes": "https"}, {"allowed_schemes": []}):
            case = valid_mandate()
            case["evidence_policy"] = policy
            with self.subTest(policy=policy):
                with self.assertRaises(ValueError):
                    p0004.validate_draft(case)

    def test_p0005_rejects_nonaddressable_refs_and_bad_text(self):
        for bad in ("https:no-host", "https:///no-host", "https://[unclosed",
                    "https://username:secret@example.org/a", "", None, "https://a b"):
            case = valid_measurement()
            case["measurement"]["source_ref"] = bad
            with self.subTest(source_ref=bad):
                with self.assertRaises(ValueError):
                    p0005.validate_draft(case)
        for field in ("id", "question", "hypothesis"):
            case = valid_measurement()
            case[field] = None
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    p0005.validate_draft(case)

    def test_p0006_rejects_non_list_tag_fields_even_when_no_pairs_match(self):
        for kind, field, value in (
            ("sources", "quality_tags", "dry"),
            ("sources", "contaminants", "toxic"),
            ("demands", "required_tags", "dry"),
            ("demands", "prohibited_contaminants", "toxic"),
            ("demands", "accepted_regions", "x"),
            ("demands", "accepted_regions", [3]),
        ):
            case = valid_lineage()
            # Deliberately eliminate material compatibility: invalid inputs must
            # still fail, not be silently skipped by the inner match loop.
            case["sources"][0]["material_code"] = "UNMATCHED"
            case[kind][0][field] = value
            with self.subTest(kind=kind, field=field, value=value):
                with self.assertRaises(ValueError):
                    p0006.build_opportunity_map(case)

    def test_p0006_rejects_finite_inputs_whose_aggregate_mass_overflows(self):
        case = valid_lineage()
        case["sources"] = [
            dict(case["sources"][0], id="S1", mass_kg=1e308),
            dict(case["sources"][0], id="S2", mass_kg=1e308),
        ]
        with self.assertRaisesRegex(ValueError, "mass totals overflowed"):
            p0006.build_opportunity_map(case)

        # A single source can be matched to two demands, inflating the pairwise
        # sum while unique source mass remains finite. Both totals need guards.
        case = valid_lineage()
        case["sources"][0]["mass_kg"] = 1e308
        case["demands"].append(dict(case["demands"][0], id="D2"))
        with self.assertRaisesRegex(ValueError, "mass totals overflowed"):
            p0006.build_opportunity_map(case)

    def test_p0007_rejects_finite_episodes_that_overflow_total_loss(self):
        case = valid_backtest()
        case["policy"]["action_cost"] = 0
        for episode in case["episodes"]:
            episode.update(warning_score=0.9, event_occurred=True,
                           baseline_loss_units=1e308, mitigated_loss_units=1e308)
        with self.assertRaisesRegex(ValueError, "totals overflowed"):
            p0007.simulate(case)

        # Aggregate can be finite but one action plus loss can overflow.
        case = valid_backtest()
        case["policy"]["action_cost"] = 1e308
        case["episodes"][0].update(
            warning_score=0.9, event_occurred=True,
            baseline_loss_units=1e308, mitigated_loss_units=1e308)
        with self.assertRaisesRegex(ValueError, "totals overflowed"):
            p0007.simulate(case)

    def test_p0003_finite_shifted_energy_and_overflow_rejection(self):
        fixture = {
            "slot_minutes": 30, "site_capacity_kw": 1e308,
            "grid_stress": [1e-10] * 3 + [0] * 3,
            "tasks": [{
                "id": "heavy", "power_kw": 1e308,
                "duration_slots": 3, "earliest_slot": 0,
                "latest_end_slot": 6, "deferrable": True, "priority": 50,
            }],
        }
        report = p0003.analyze_workload(fixture)
        self.assertEqual(report["moved_task_ids"], ["heavy"])
        self.assertTrue(math.isfinite(report["planned_shifted_energy_kwh"]))
        self.assertAlmostEqual(report["planned_shifted_energy_kwh"], 1.5e308)
        self.assertFalse(report["truth_boundary"]["physical_savings_claimed"])

        second = copy.deepcopy(fixture)
        second["grid_stress"] = [1e-10] * 4 + [0] * 4
        second["tasks"][0]["duration_slots"] = 2
        second["tasks"][0]["latest_end_slot"] = 8
        second["tasks"].append(dict(second["tasks"][0], id="other"))
        with self.assertRaisesRegex(ValueError, "shifted energy"):
            p0003.analyze_workload(second)

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
