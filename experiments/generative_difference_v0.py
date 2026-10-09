"""Falsifiable toy test: does retaining an option beat immediate extraction?

This is an intervention in a *software repository*, not a claim of direct
physical or paranormal action. It does not establish historical novelty.
Run: python3 experiments/generative_difference_v0.py
"""
from fractions import Fraction

OPPORTUNITY_PROBABILITY = Fraction(2, 5)
EXTRACT_NOW = 10
PRESERVE_NOW = 6
OPTION_PAYOFF_IF_OPPORTUNITY = 20


def outcome(policy: str, opportunity: bool) -> int:
    if policy == "extract":
        return EXTRACT_NOW
    if policy == "preserve":
        return PRESERVE_NOW + (OPTION_PAYOFF_IF_OPPORTUNITY if opportunity else 0)
    raise ValueError("Unknown policy")


def expected(policy: str) -> Fraction:
    return (
        (1 - OPPORTUNITY_PROBABILITY) * outcome(policy, False)
        + OPPORTUNITY_PROBABILITY * outcome(policy, True)
    )


def run() -> None:
    # Same two possible worlds, same probability, both policies compared.
    assert outcome("extract", False) == 10
    assert outcome("extract", True) == 10
    assert outcome("preserve", False) == 6
    assert outcome("preserve", True) == 26

    baseline = expected("extract")
    candidate = expected("preserve")
    assert baseline == 10
    assert candidate == 14
    assert candidate - baseline == 4

    # Crucial negative control: preservation is NOT always better.
    assert outcome("preserve", False) < outcome("extract", False)

    # Boundary: at p <= 0.2, preserving does not outperform extraction.
    threshold = Fraction(EXTRACT_NOW - PRESERVE_NOW, OPTION_PAYOFF_IF_OPPORTUNITY)
    assert threshold == Fraction(1, 5)
    print("model=two-stage synthetic counterfactual")
    print(f"p_opportunity={OPPORTUNITY_PROBABILITY}")
    print(f"baseline_expected={baseline}")
    print(f"preserve_expected={candidate}")
    print(f"expected_delta={candidate - baseline}")
    print(f"threshold_p={threshold}")
    print("no_opportunity_result=preserve loses by 4")
    print("claim_scope=toy-model only; no physical anomaly or global novelty verified")


if __name__ == "__main__":
    run()
