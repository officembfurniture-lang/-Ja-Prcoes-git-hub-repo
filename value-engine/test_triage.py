import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import triage


REF = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


def obs(title: str, body: str = "", **overrides):
    value = {
        "fingerprint": overrides.pop("fingerprint", title),
        "source": "github_public_demand",
        "signal_query": "is:issue is:open bounty",
        "url": overrides.pop("url", f"https://github.com/example/repo/issues/{abs(hash(title))}"),
        "title": title,
        "body_excerpt": body,
        "created_at": "2026-09-10T10:00:00Z",
        "updated_at": "2026-09-11T10:00:00Z",
        "detected_at": "2026-09-11T12:00:00Z",
        "status": "OBSERVED",
        "primary_source_verified": False,
        "demand_or_reward_verified": False,
        "delivery_route": None,
        "settlement_route": None,
        "realized_value": 0,
    }
    value.update(overrides)
    return value


class ClassifyTests(unittest.TestCase):
    def test_funded_agent_friendly_candidate_enters_verify_queue(self):
        item = triage.classify(
            obs(
                "[BOUNTY $400] Implement deterministic validator",
                "Funded reward. Acceptance criteria: tests green. "
                "Autonomous agents welcome. Submit a pull request. Payment is released on merge.",
            ),
            REF,
        )
        self.assertEqual(item["disposition"], "QUEUE_VERIFY")
        self.assertFalse(item["primary_source_verified"])
        self.assertEqual(item["realized_value"], 0)

    def test_proposed_reward_is_not_queued(self):
        item = triage.classify(
            obs(
                "Paid proposal: SRT export ($75 proposed)",
                "Please confirm whether the proposed reward is approved. "
                "This is not a claim of an existing funded bounty.",
            ),
            REF,
        )
        self.assertEqual(item["disposition"], "HOLD_REWARD_UNCONFIRMED")
        self.assertIn("reward_not_yet_confirmed", item["risks"])

    def test_signup_or_maintainer_confirmation_becomes_human_gate(self):
        item = triage.classify(
            obs(
                "[PAID BOUNTY - $660] UI feature",
                "Acceptance criteria known. Sign up first. Maintainer must confirm before work begins. "
                "Payment is made after merge.",
            ),
            REF,
        )
        self.assertEqual(item["disposition"], "HOLD_HUMAN_GATE")

    def test_capital_requirement_blocks_autonomous_queue(self):
        item = triage.classify(
            obs(
                "[BOUNTY 2 USDC] Agent task",
                "Funded and escrowed. Acceptance criteria known. Agents welcome. "
                "Requires a 0.01 USDC claim bond and fully fund that child before claiming.",
            ),
            REF,
        )
        self.assertEqual(item["disposition"], "HOLD_CAPITAL_REQUIRED")
        self.assertIn("capital_required", item["risks"])

    def test_explicit_do_not_start_has_highest_hold_priority(self):
        item = triage.classify(
            obs(
                "[BOUNTY 2 USDC] Incomplete mirror",
                "Funded. Agents welcome. Do not start, claim, sign, or spend from this incomplete mirror.",
            ),
            REF,
        )
        self.assertEqual(item["disposition"], "HOLD_START_PROHIBITED")

    def test_radar_mirror_never_enters_verify_queue_directly(self):
        item = triage.classify(
            obs(
                "[radar] OPEN_BOUNTY 700000 sats",
                "Bounty alert with reward and acceptance criteria.",
                url="https://github.com/relayhop/sn-monetization-runtime/issues/903",
            ),
            REF,
        )
        self.assertEqual(item["disposition"], "HOLD_PRIMARY_SOURCE")


class PipelineTests(unittest.TestCase):
    def test_newest_record_per_url_wins(self):
        same_url = "https://github.com/example/repo/issues/1"
        older = obs(
            "old",
            "bounty $100",
            url=same_url,
            fingerprint="old",
            detected_at="2026-09-10T10:00:00Z",
        )
        newer = obs(
            "new",
            "bounty $100 funded acceptance criteria autonomous agents submit a pull request payment is released",
            url=same_url,
            fingerprint="new",
            detected_at="2026-09-11T10:00:00Z",
        )
        values = triage.newest_by_url([older, newer])
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0]["fingerprint"], "new")

    def test_run_emits_only_verify_candidates_and_never_realized_value(self):
        good = obs(
            "[BOUNTY $250] Good",
            "Funded. Acceptance criteria. Autonomous agents welcome. Submit a pull request. Payment is released on merge.",
            url="https://github.com/example/good/issues/1",
        )
        blocked = obs(
            "[BOUNTY $250] Blocked",
            "Funded. Acceptance criteria. Sign up and wait for confirmation.",
            url="https://github.com/example/blocked/issues/1",
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "observations.ndjson"
            queue = root / "queue.ndjson"
            summary = root / "summary.json"
            source.write_text(
                "\n".join(json.dumps(value) for value in (good, blocked)) + "\n",
                encoding="utf-8",
            )
            result = triage.run(source, queue, summary, limit=50)
            queued = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(result["verify_queue_emitted"], 1)
            self.assertEqual(len(queued), 1)
            self.assertEqual(queued[0]["url"], good["url"])
            self.assertEqual(queued[0]["realized_value"], 0)
            self.assertFalse(queued[0]["primary_source_verified"])


if __name__ == "__main__":
    unittest.main()
