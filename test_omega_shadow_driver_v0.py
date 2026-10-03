import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from omega_shadow_driver_v0 import evaluate, PROVENANCE_KINDS, stable_hash

ROOT = Path(__file__).resolve().parent


class OmegaShadowDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "omega_shadow_fixtures_v1.json").open(encoding="utf-8") as f:
            cls.cases = json.load(f)["cases"]

    def record(self):
        return deepcopy(next(c["record"] for c in self.cases if c["name"] == "verified_material_delta"))

    def action(self):
        return {
            "executed": True, "readback_verified": True,
            "provenance": {"kind": "artifact_readback", "locator": "fixture://action", "readback_verified": True},
            "supporting_evidence_ids": ["e1"],
        }

    def test_fixtures(self):
        for case in self.cases:
            with self.subTest(case=case["name"]):
                verdict = evaluate(case["record"])
                self.assertEqual(verdict.verdict, case["expected_verdict"])

    def test_progress_references_must_resolve_to_verified_evidence(self):
        for refs in ([], ["missing"], ["e1", "missing"], ["pending"]):
            with self.subTest(refs=refs):
                record = self.record()
                record["evidence"].append({"id": "pending", "status": "OBSERVED"})
                record["predictions"] = [{"status": "PROGRESS", "supporting_evidence_ids": refs}]
                self.assertEqual(evaluate(record).verdict, "DRIVER_REGRESSION")

    def test_verified_progress_support_does_not_bypass_effect_gate(self):
        record = self.record()
        record["decision_effect"] = {}
        record["predictions"] = [{"status": "PROGRESS", "supporting_evidence_ids": ["e1"]}]
        self.assertEqual(evaluate(record).verdict, "HOLD")

    def test_action_requires_resolved_references_and_readback(self):
        for change in ({"supporting_evidence_ids": []}, {"supporting_evidence_ids": ["missing"]}, {"readback_verified": False}):
            with self.subTest(change=change):
                record = self.record()
                record["action"] = self.action() | change
                result = evaluate(record)
                self.assertEqual(result.verdict, "HOLD")
                self.assertFalse(result.action_verified)

    def test_resolved_action_with_known_evidence_can_be_new(self):
        record = self.record()
        record["evidence"][0]["already_known"] = True
        record["action"] = self.action()
        result = evaluate(record)
        self.assertEqual(result.verdict, "PROMOTE")
        self.assertEqual(result.evidence_delta, 0)
        self.assertTrue(result.action_verified)

    def test_effect_requires_resolved_evidence_references(self):
        for refs in ([], ["missing"], ["e1", "missing"]):
            with self.subTest(refs=refs):
                record = self.record()
                record["decision_effect"]["supporting_evidence_ids"] = refs
                self.assertEqual(evaluate(record).verdict, "HOLD")
                self.assertFalse(evaluate(record).material_effect_verified)

    def test_nonfinite_or_nonjson_states_fail_closed_with_safe_hash(self):
        for key in ("previous_state", "candidate_state"):
            for value in (float("nan"), float("inf"), {1, 2}, (1, 2), "\ud800"):
                with self.subTest(key=key, value=repr(value)):
                    record = self.record()
                    record[key] = {"bad": value}
                    result = evaluate(record)
                    self.assertEqual(result.verdict, "INPUT_INVALID")
                    expected = {} if key == "previous_state" else record["previous_state"]
                    self.assertEqual(result.state_hash, stable_hash(expected))
                    json.dumps(asdict(result), allow_nan=False)

    def test_numeric_fields_reject_coercion_null_and_nonfinite_values(self):
        fields = [("human_burden", "before"), ("human_burden", "after"), ("debts", "claim_debt")]
        for parent, key in fields:
            for value in (None, True, False, "0", -1, float("nan"), float("inf"), 10 ** 400):
                with self.subTest(field=(parent, key), value=repr(value)):
                    record = self.record()
                    record[parent][key] = value
                    self.assertEqual(evaluate(record).verdict, "INPUT_INVALID")

    def test_debt_limits_and_totals_must_be_finite_nonnegative(self):
        for value in (None, True, "3", -1, float("inf"), float("nan")):
            with self.subTest(limit=value):
                record = self.record()
                record["debt_limit"] = value
                self.assertEqual(evaluate(record).verdict, "INPUT_INVALID")
        record = self.record()
        record["debts"] = {"claim_debt": 1e308, "prediction_debt": 1e308}
        self.assertEqual(evaluate(record).verdict, "INPUT_INVALID")

    def test_debt_boundary_and_unknown_debt_name(self):
        record = self.record()
        record["debt_limit"] = 3
        record["debts"] = {"claim_debt": 3}
        self.assertEqual(evaluate(record).verdict, "PROMOTE")
        record["debts"]["claim_debt"] = 3.01
        self.assertEqual(evaluate(record).verdict, "HOLD")
        record["debts"] = {"claims_debt": 4}
        self.assertEqual(evaluate(record).verdict, "INPUT_INVALID")

    def test_unknown_burden_is_not_zero_or_invalid(self):
        for burden in ({}, {"measured": False}, {"measured": False, "before": 0, "after": 0}):
            with self.subTest(burden=burden):
                record = self.record()
                record["human_burden"] = burden
                result = evaluate(record)
                self.assertEqual(result.verdict, "HOLD")
                self.assertIsNone(result.burden_delta)

    def test_measured_burden_requires_explicit_complete_measurements(self):
        for burden in ({"before": 0, "after": 0}, {"measured": True, "before": 0}, {"measured": True, "after": 0}):
            with self.subTest(burden=burden):
                record = self.record()
                record["human_burden"] = burden
                self.assertEqual(evaluate(record).verdict, "INPUT_INVALID")

    def test_positive_burden_blocks_promotion_with_material_effect(self):
        record = self.record()
        record["human_burden"] = {"measured": True, "before": 1, "after": 2}
        result = evaluate(record)
        self.assertTrue(result.material_effect_verified)
        self.assertEqual(result.burden_delta, 1)
        self.assertEqual(result.verdict, "DRIVER_REGRESSION")

    def test_verified_evidence_needs_allowlisted_structured_provenance(self):
        for value in ("readback", {}, {"kind": "unrecognized", "locator": "fixture://x", "readback_verified": True}, {"kind": "test_run", "locator": " ", "readback_verified": True}):
            with self.subTest(value=value):
                record = self.record()
                record["evidence"][0]["provenance"] = value
                self.assertEqual(evaluate(record).verdict, "INPUT_INVALID")
        for kind in PROVENANCE_KINDS:
            with self.subTest(kind=kind):
                record = self.record()
                record["evidence"][0]["provenance"]["kind"] = kind
                self.assertEqual(evaluate(record).verdict, "PROMOTE")

    def test_unverified_provenance_cannot_support_progress(self):
        record = self.record()
        record["evidence"][0]["provenance"]["readback_verified"] = False
        record["predictions"] = [{"status": "PROGRESS", "supporting_evidence_ids": ["e1"]}]
        self.assertEqual(evaluate(record).verdict, "DRIVER_REGRESSION")

    def test_blank_duplicate_and_malformed_evidence_ids_are_rejected(self):
        for value in ("", " ", None, [], 1):
            with self.subTest(value=value):
                record = self.record()
                record["evidence"][0]["id"] = value
                self.assertEqual(evaluate(record).verdict, "INPUT_INVALID")
        record = self.record()
        record["evidence"].append(deepcopy(record["evidence"][0]))
        self.assertEqual(evaluate(record).verdict, "INPUT_INVALID")

    def test_malformed_containers_and_flags_fail_closed(self):
        for key, value in (("evidence", None), ("evidence", [None]), ("predictions", [1]), ("action", []), ("human_burden", None), ("candidate_state", [])):
            with self.subTest(key=key, value=value):
                record = self.record()
                record[key] = value
                self.assertEqual(evaluate(record).verdict, "INPUT_INVALID")
        for value in (1, "true", None):
            with self.subTest(flag=value):
                record = self.record()
                record["human_burden"]["measured"] = value
                self.assertEqual(evaluate(record).verdict, "INPUT_INVALID")
        for record in (None, [], "record"):
            self.assertEqual(evaluate(record).verdict, "INPUT_INVALID")

    def test_malformed_reference_lists_are_rejected(self):
        for refs in ("e1", [""], [1], ["e1", "e1"], None):
            with self.subTest(refs=refs):
                record = self.record()
                record["predictions"] = [{"status": "PROGRESS", "supporting_evidence_ids": refs}]
                self.assertEqual(evaluate(record).verdict, "INPUT_INVALID")

    def test_input_is_not_mutated_and_key_order_does_not_change_result(self):
        record = self.record()
        before = deepcopy(record)
        first = asdict(evaluate(record))
        self.assertEqual(record, before)
        self.assertEqual(first, asdict(evaluate(dict(reversed(list(record.items()))))))

    def test_legacy_receipt_is_preserved_and_not_silently_upgraded(self):
        path = ROOT / "shadow_results" / "p0003_distribution_shadow_v0.json"
        old_result = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(old_result["post_repair"]["p0003_shadow_verdict"], "HOLD")
        old_cases = json.loads((ROOT / "omega_shadow_fixtures_v0.json").read_text())["cases"]
        for case in old_cases:
            with self.subTest(legacy=case["name"]):
                self.assertEqual(evaluate(case["record"]).verdict, "INPUT_INVALID")

    def test_cli_emits_strict_json_from_another_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            path.write_text(json.dumps(self.record()), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(ROOT / "omega_shadow_driver_v0.py"), str(path)], cwd=directory, text=True, capture_output=True, check=True)
            result = json.loads(completed.stdout)
            self.assertEqual(result["verdict"], "PROMOTE")


if __name__ == "__main__":
    unittest.main()
