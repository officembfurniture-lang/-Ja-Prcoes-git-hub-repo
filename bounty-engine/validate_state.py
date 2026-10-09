import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_json(path: Path):
    def reject_constant(value):
        raise AssertionError(f"{path.name}: non-finite JSON constant {value}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def _non_negative_number(value, label: str) -> None:
    assert type(value) in (int, float), f"{label} must be numeric, not boolean/coerced text"
    assert math.isfinite(float(value)) and value >= 0, f"{label} must be finite and non-negative"


def validate(root: Path = ROOT) -> None:
    state = _load_json(root / "state.json")
    assert isinstance(state, dict), "state must be an object"

    required = {
        "engine", "cycle", "state", "active_bounty", "realized_value_usd",
        "submitted", "accepted", "paid", "human_gates",
    }
    missing = required - state.keys()
    assert not missing, f"missing state keys: {sorted(missing)}"
    assert state["engine"] == "BOUNTY_ENGINE_v1", "unexpected engine identifier"
    assert type(state["cycle"]) is int and state["cycle"] >= 0, "cycle must be a non-negative integer"
    _non_negative_number(state["realized_value_usd"], "realized_value_usd")

    for key in ("submitted", "accepted", "paid", "human_gates"):
        assert type(state[key]) is int and state[key] >= 0, f"{key} must be a non-negative integer"

    assert state["paid"] <= state["accepted"] <= state["submitted"], (
        "paid <= accepted <= submitted invariant violated"
    )
    if state["state"] == "IDLE":
        assert state["active_bounty"] is None, "IDLE cannot have active_bounty"

    ledger = root / "ledger.ndjson"
    paid_rows = accepted_rows = submitted_rows = 0
    for line_number, raw in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(
                raw,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    AssertionError(f"line {line_number}: non-finite JSON constant {value}")
                ),
            )
        except json.JSONDecodeError as exc:
            raise AssertionError(f"line {line_number}: invalid JSON: {exc}") from exc
        assert isinstance(row, dict), f"line {line_number}: ledger row must be an object"

        realized = row.get("realized_value_usd", 0)
        _non_negative_number(realized, f"line {line_number}: realized_value_usd")

        for flag in ("submitted", "accepted", "paid"):
            if flag in row:
                assert type(row[flag]) is bool, f"line {line_number}: {flag} must be boolean"

        submitted = row.get("submitted") is True
        accepted = row.get("accepted") is True
        paid = row.get("paid") is True
        if paid:
            assert accepted, f"line {line_number}: paid without accepted"
            assert submitted, f"line {line_number}: paid without submitted"
        if accepted:
            assert submitted, f"line {line_number}: accepted without submitted"
        submitted_rows += int(submitted)
        accepted_rows += int(accepted)
        paid_rows += int(paid)

    # Ledger can contain multiple diagnostic rows per cycle, but state may never
    # claim fewer terminal events than are explicitly evidenced in the ledger.
    assert state["submitted"] >= submitted_rows, "submitted counter is below explicit ledger evidence"
    assert state["accepted"] >= accepted_rows, "accepted counter is below explicit ledger evidence"
    assert state["paid"] >= paid_rows, "paid counter is below explicit ledger evidence"


def main() -> None:
    validate()
    print("BOUNTY_ENGINE state/ledger validation: OK")


if __name__ == "__main__":
    main()
