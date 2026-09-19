"""Isolated validator regressions; all changed states and receipts are synthetic."""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("engine_validator_under_test", HERE / "validate.py")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)
GATES = (
    "primary_source_verified", "demand_or_reward_verified", "acceptance_criteria_known",
    "delivery_route_verified_before_production", "settlement_route_verified_before_production",
    "safety_and_legality_pass",
)
PHASES = ("PRODUCE", "VALIDATE", "DELIVER", "OBSERVE", "SETTLE")


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("state.json", "policy.json", "routes.json", "sources.json", "outcomes.ndjson"):
            path = HERE / name
            if path.exists():
                (self.root / name).write_bytes(path.read_bytes())
        self.state = json.loads((self.root / "state.json").read_text())
        self.state.update({
            "phase": "IDLE", "active_opportunity": None, "active_route": None,
            "lease": dict.fromkeys(("cycle_id", "owner", "acquired_at", "expires_at")),
            "realized": {"cash": [], "verified_non_cash": [], "cost_savings": []},
            "counters": {"observed": 2, "verified": 2, "selected": 2, "produced": 2,
                         "delivered": 2, "accepted": 2, "paid": 0, "human_gates": 0},
        })
        rows = []
        for suffix in ("one", "two"):
            row = self.paid_receipt()
            row.update(opportunity_id=f"synthetic-{suffix}", status="ACCEPTED", payment_evidence=None)
            del row["received_at"]
            rows.append(row)
        self.write_outcomes(rows)

    def write_state(self):
        (self.root / "state.json").write_text(json.dumps(self.state))

    def check(self):
        self.write_state()
        with patch.object(validator, "ROOT", self.root), contextlib.redirect_stdout(io.StringIO()):
            return validator.main()

    def reject(self):
        with self.assertRaises(AssertionError):
            self.check()

    def production(self, phase="PRODUCE"):
        self.state["phase"] = phase
        self.state["lease"] = {
            "cycle_id": "synthetic-validation", "owner": "fixture-only",
            "acquired_at": "2026-09-19T10:00:00Z", "expires_at": "2026-09-19T10:45:00Z",
        }
        self.state["active_opportunity"] = {
            "id": "synthetic-only", "delivery_route": "github_direct_write",
            "settlement_route": "native_platform_submission", **{gate: True for gate in GATES},
        }

    def paid_receipt(self):
        return {
            "opportunity_id": "synthetic-only", "status": "PAID", "amount": 1,
            "currency": "TEST", "delivery_evidence": "fixture://delivery",
            "acceptance_evidence": "fixture://acceptance", "accepted_at": "2026-09-19T10:00:00Z",
            "payment_evidence": "fixture://payment", "received_at": "2026-09-19T11:00:00Z",
        }

    def write_outcomes(self, rows):
        (self.root / "outcomes.ndjson").write_text("".join(json.dumps(row) + "\n" for row in rows))

    def test_real_persisted_idle_state_is_preserved(self):
        names = ("state.json", "policy.json", "routes.json", "sources.json", "outcomes.ndjson")
        before = {name: (HERE / name).read_bytes() for name in names if (HERE / name).exists()}
        with patch.object(validator, "ROOT", HERE), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(validator.main(), 0)
        self.assertEqual({name: (HERE / name).read_bytes() for name in before}, before)

    def test_valid_production_contract_for_each_phase(self):
        for phase in PHASES:
            with self.subTest(phase=phase):
                self.production(phase)
                self.assertEqual(self.check(), 0)

    def test_production_requires_an_active_opportunity(self):
        for phase in PHASES:
            for active in (None, {}, [], "not-an-opportunity"):
                with self.subTest(phase=phase, active=active):
                    self.production(phase)
                    self.state["active_opportunity"] = active
                    self.reject()

    def test_production_requires_an_identifier(self):
        for value in (None, "", "   ", True):
            with self.subTest(value=value):
                self.production()
                self.state["active_opportunity"]["id"] = value
                self.reject()

    def test_every_opportunity_gate_requires_literal_true(self):
        for gate in GATES:
            for value in (None, False, 1, "true"):
                with self.subTest(gate=gate, value=value):
                    self.production()
                    self.state["active_opportunity"][gate] = value
                    self.reject()

    def test_policy_flags_cannot_replace_opportunity_verification(self):
        self.production()
        for gate in GATES:
            del self.state["active_opportunity"][gate]
        self.reject()

    def test_unknown_delivery_and_settlement_routes(self):
        for field in ("delivery_route", "settlement_route"):
            with self.subTest(field=field):
                self.production()
                self.state["active_opportunity"][field] = "not-in-registry"
                self.reject()

    def test_non_execution_and_wrong_role_routes(self):
        for field, route in (
            ("delivery_route", "github_external_read_only"),
            ("delivery_route", "artifact_only"), ("delivery_route", "human_gate"),
            ("settlement_route", "github_direct_write"),
            ("settlement_route", "github_actions_public_http"),
        ):
            with self.subTest(field=field, route=route):
                self.production()
                self.state["active_opportunity"][field] = route
                self.reject()

    def test_runtime_verification_can_supersede_old_registry_test_flag(self):
        self.production()
        routes = json.loads((self.root / "routes.json").read_text())
        target = next(row for row in routes["routes"] if row["id"] == "native_platform_submission")
        self.assertIs(target["verified_in_test"], False)
        self.assertEqual(self.check(), 0)

    def test_production_requires_a_lease(self):
        self.production()
        self.state["lease"] = dict.fromkeys(("cycle_id", "owner", "acquired_at", "expires_at"))
        self.reject()

    def test_partial_empty_malformed_and_reversed_leases(self):
        for key, value in (("owner", None), ("owner", ""), ("owner", False),
                           ("acquired_at", "yesterday"), ("acquired_at", "2026-09-19T10:00:00"),
                           ("expires_at", "2026-09-19T09:00:00Z")):
            with self.subTest(key=key, value=value):
                self.production()
                self.state["lease"][key] = value
                self.reject()

    def test_idle_rejects_active_route_and_lease(self):
        original = copy.deepcopy(self.state)
        for patch_value in ({"active_route": "github_direct_write"}, {"lease": {"owner": "fixture"}}):
            with self.subTest(patch_value=patch_value):
                self.state = copy.deepcopy(original)
                self.state.update(patch_value)
                self.reject()

    def test_boolean_negative_and_fractional_counters(self):
        for value in (True, False, -1, 1.5, "2"):
            with self.subTest(value=value):
                self.state["counters"]["human_gates"] = value
                self.reject()

    def test_existing_counter_order_control(self):
        self.state["counters"]["accepted"] = self.state["counters"]["delivered"] + 1
        self.reject()

    def test_cash_amount_requires_positive_finite_number(self):
        for value in (-1, 0, True, "3", float("nan"), float("inf")):
            with self.subTest(value=value):
                self.state["realized"]["cash"] = [{"amount": value, "currency": "TEST",
                    "evidence": "fixture://cash", "received_at": "2026-09-19T10:00:00Z"}]
                self.reject()

    def test_cash_requires_receipt_and_zoned_timestamp(self):
        valid = {"amount": 1, "currency": "TEST", "evidence": "fixture://cash",
                 "received_at": "2026-09-19T10:00:00Z"}
        for key, value in (("currency", ""), ("evidence", True), ("evidence", " "),
                           ("received_at", "today"), ("received_at", "2026-09-19")):
            with self.subTest(key=key, value=value):
                self.state["realized"]["cash"] = [dict(valid, **{key: value})]
                self.reject()

    def test_paid_counter_cannot_advance_from_acceptance_only(self):
        self.state["counters"]["paid"] = 1
        self.reject()

    def test_paid_receipt_requires_payment_evidence_and_time(self):
        for key in ("payment_evidence", "received_at", "acceptance_evidence", "delivery_evidence"):
            with self.subTest(key=key):
                row = self.paid_receipt()
                del row[key]
                self.write_outcomes([row])
                self.state["counters"]["paid"] = 1
                self.reject()

    def test_well_formed_synthetic_paid_receipt_is_only_structurally_valid(self):
        self.write_outcomes([self.paid_receipt()])
        self.state["counters"]["paid"] = 1
        self.assertEqual(self.check(), 0)

    def test_duplicate_paid_receipt_is_rejected(self):
        self.write_outcomes([self.paid_receipt(), self.paid_receipt()])
        self.state["counters"]["paid"] = 2
        self.reject()

    def test_paid_receipt_requires_corresponding_counter(self):
        self.write_outcomes([self.paid_receipt()])
        self.state["counters"]["paid"] = 0
        self.reject()

    def test_payment_cannot_predate_acceptance(self):
        row = self.paid_receipt()
        row["received_at"] = "2026-09-18T10:00:00Z"
        self.write_outcomes([row])
        self.state["counters"]["paid"] = 1
        self.reject()

    def test_outcomes_file_is_actually_validated(self):
        for content in ('{"bad":', '[]\n', '{"status": "ACCEPTED"}\n'):
            with self.subTest(content=content):
                (self.root / "outcomes.ndjson").write_text(content)
                with self.assertRaises((AssertionError, json.JSONDecodeError)):
                    self.check()

    def test_malformed_registries_and_state_containers_fail_closed(self):
        for name, field, value in (("routes.json", "routes", [None]),
                                    ("routes.json", "routes", [{"id": []}]),
                                    ("sources.json", "sources", {})):
            with self.subTest(name=name, value=value):
                original = (self.root / name).read_text()
                data = json.loads(original)
                data[field] = value
                (self.root / name).write_text(json.dumps(data))
                self.reject()
                (self.root / name).write_text(original)
        self.state["counters"] = []
        self.reject()


if __name__ == "__main__":
    unittest.main()
