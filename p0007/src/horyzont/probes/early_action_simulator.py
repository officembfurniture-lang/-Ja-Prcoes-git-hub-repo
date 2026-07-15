from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA = "horyzont.early-action-backtest/v0.1"


def simulate(payload: dict[str, Any]) -> dict[str, Any]:
    episodes = payload.get("episodes")
    policy = payload.get("policy", {})
    if not isinstance(episodes, list) or len(episodes) < 2:
        raise ValueError("at least two historical or synthetic episodes are required")
    threshold = float(policy.get("warning_threshold", -1))
    minimum_lead = float(policy.get("minimum_lead_hours", -1))
    action_cost = float(policy.get("action_cost", -1))
    if not 0 <= threshold <= 1 or minimum_lead < 0 or action_cost < 0:
        raise ValueError("policy threshold, lead time or action cost is invalid")

    rows = []
    baseline_total = 0.0
    simulated_total = 0.0
    tp = fp = tn = fn = 0
    identifiers: set[str] = set()
    for episode in episodes:
        identifier = str(episode.get("id", "")).strip()
        if not identifier or identifier in identifiers:
            raise ValueError("episode ids must be non-empty and unique")
        identifiers.add(identifier)
        warning = float(episode["warning_score"])
        lead = float(episode["lead_hours"])
        baseline_loss = float(episode["baseline_loss_units"])
        mitigated_loss = float(episode["mitigated_loss_units"])
        occurred = bool(episode["event_occurred"])
        if not 0 <= warning <= 1 or lead < 0 or baseline_loss < 0 or mitigated_loss < 0:
            raise ValueError(f"invalid episode values for {identifier}")
        if mitigated_loss > baseline_loss:
            raise ValueError("mitigated loss cannot exceed baseline loss")

        action = warning >= threshold and lead >= minimum_lead
        baseline_episode = baseline_loss if occurred else 0.0
        simulated_episode = (
            (mitigated_loss if action else baseline_loss) if occurred else 0.0
        ) + (action_cost if action else 0.0)
        baseline_total += baseline_episode
        simulated_total += simulated_episode
        if action and occurred:
            tp += 1
        elif action and not occurred:
            fp += 1
        elif not action and occurred:
            fn += 1
        else:
            tn += 1
        rows.append(
            {
                "episode_id": identifier,
                "simulated_action": action,
                "event_occurred": occurred,
                "baseline_loss_units": baseline_episode,
                "simulated_total_units": simulated_episode,
            }
        )
    return {
        "schema": SCHEMA,
        "policy": policy,
        "episodes": rows,
        "confusion_matrix": {
            "true_positive": tp,
            "false_positive": fp,
            "true_negative": tn,
            "false_negative": fn,
        },
        "baseline_total_loss_units": round(baseline_total, 6),
        "simulated_total_cost_units": round(simulated_total, 6),
        "modeled_avoided_loss_units": round(baseline_total - simulated_total, 6),
        "truth_boundary": {
            "input_kind": payload.get("input_kind", "unspecified"),
            "real_warning_issued": False,
            "real_action_taken": False,
            "real_avoided_loss_established": False,
            "statement": (
                "This is a counterfactual backtest. Its modeled avoided loss is not an "
                "observed outcome, financial saving or authorization for emergency action."
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest a bounded early-action policy")
    parser.add_argument("input", help="Historical or synthetic episode JSON")
    parser.add_argument("--output", help="Optional result JSON path")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rendered = json.dumps(simulate(payload), ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
