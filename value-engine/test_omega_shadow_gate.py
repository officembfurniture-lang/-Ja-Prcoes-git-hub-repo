"""Tests for bounded Omega shadow-only paired safety trials."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest
from types import SimpleNamespace

import omega_shadow_gate as gate


STAMP = "2026-10-11T15:38:03Z"
SOURCE_REVISION = "a" * 40


def observation(i):
    return {
        "url": f"https://github.com/example/repo/issues/{i}",
        "fingerprint": f"revision-{i}",
        "title": "$100 bounty task",
        "body_excerpt": "Funded. Acceptance criteria: tests. Submit PR.",
        "source": "github_public_demand",
        "signal_query": "is:issue is:open bounty",
        "created_at": "2026-10-10T10:00:00Z",
        "updated_at": "2026-10-11T09:00:00Z",
        "detected_at": "2026-10-11T12:00:00Z",
        "status": "OBSERVED",
        "primary_source_verified": False,
        "demand_or_reward_verified": False,
        "delivery_route": None,
        "settlement_route": None,
        "realized_value": 0,
    }


def bytes_and_state(rows):
    raw = "".join(json.dumps(item, sort_keys=True) + "\n"
                  for item in rows).encode("utf-8")
    state = {
        "engine": "VALUE_ENGINE_v2",
        "last_cycle_result": {
            "cycle_id": "cycle-238-synthetic",
            "at": STAMP,
            "observations_sha256": hashlib.sha256(raw).hexdigest(),
        },
    }
    return raw, state


def safe_evaluator(record):
    assert record["human_burden"] == {"measured": False}
    assert record["decision_effect"] == {}
    assert all(e["status"] == "OBSERVED" for e in record["evidence"])
    assert record["previous_state"] == record["candidate_state"]
    return SimpleNamespace(verdict="NO_DELTA", action_verified=False,
                           material_effect_verified=False, evidence_delta=0)


class ShadowGateTests(unittest.TestCase):
    def test_real_observation_shape_yields_safety_bridge_not_promotion(self):
        raw, state = bytes_and_state([observation(i) for i in range(1, 21)])
        report = gate.trial(state, raw, safe_evaluator, SOURCE_REVISION)
        self.assertEqual(report["sample_size"], 16)
        self.assertEqual(report["omega_verdict_counts"], {"NO_DELTA": 16})
        self.assertEqual(report["promotion_gate"], "HOLD")
        self.assertFalse(report["human_correction_burden_measured"])
        self.assertFalse(report["external_result_verified"])
        self.assertTrue(report["same_input_for_baseline_and_candidate"])
        self.assertTrue(all(not x["promoted"] for x in report["cases"]))

    def test_sample_selects_by_identity_not_input_order_or_outcome(self):
        rows = [observation(i) for i in range(1, 21)]
        first, state1 = bytes_and_state(rows)
        second, state2 = bytes_and_state(list(reversed(rows)))
        a = gate.trial(state1, first, safe_evaluator, SOURCE_REVISION)
        b = gate.trial(state2, second, safe_evaluator, SOURCE_REVISION)
        self.assertEqual([x["source_url_sha256"] for x in a["cases"]],
                         [x["source_url_sha256"] for x in b["cases"]])

    def test_invalid_or_unmatched_sensor_bytes_are_not_accepted(self):
        raw, state = bytes_and_state([observation(1)])
        tampered = raw.replace(b"Bounty", b"FAKERY")
        with self.assertRaisesRegex(ValueError, "do not match"):
            gate.trial(state, tampered, safe_evaluator, SOURCE_REVISION)
        changed = copy.deepcopy(state)
        changed["last_cycle_result"]["observations_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "do not match"):
            gate.trial(changed, raw, safe_evaluator, SOURCE_REVISION)

    def test_candidate_false_promotion_or_verified_effect_is_regression(self):
        raw, state = bytes_and_state([observation(1)])
        for verdict, action, effect in [
            ("PROMOTE", False, False),
            ("HOLD", True, False),
            ("HOLD", False, True),
        ]:
            with self.subTest(verdict=verdict, action=action, effect=effect):
                def fake(record):
                    return SimpleNamespace(verdict=verdict, action_verified=action,
                                           material_effect_verified=effect,
                                           evidence_delta=0)
                with self.assertRaises(ValueError):
                    gate.trial(state, raw, fake, SOURCE_REVISION)

    def test_sample_is_bounded_and_empty_eligible_fail_closed(self):
        raw, state = bytes_and_state([observation(1)])
        for size in (0, -1, True, 17, "16"):
            with self.subTest(size=size):
                with self.assertRaises(ValueError):
                    gate.trial(state, raw, safe_evaluator, SOURCE_REVISION, limit=size)
        bad = observation(1)
        bad["primary_source_verified"] = True
        other, bad_state = bytes_and_state([bad])
        with self.assertRaisesRegex(ValueError, "no valid real observations"):
            gate.trial(bad_state, other, safe_evaluator, SOURCE_REVISION)

    def test_duplicated_historical_source_has_single_pair(self):
        old = observation(1)
        new = dict(old, fingerprint="newer", updated_at="2026-10-11T10:00:00Z")
        raw, state = bytes_and_state([old, new, observation(2)])
        result = gate.trial(state, raw, safe_evaluator, SOURCE_REVISION)
        self.assertEqual(result["sample_size"], 2)


if __name__ == "__main__":
    unittest.main()
