"""Falsifiable toy experiment: reachability vs resilience in finite state spaces.

Run: python experiments/generative_difference.py
No claim about consciousness, quantum effects, or new physics.
"""
from collections import deque


def reachable(edges, start=0):
    seen = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for source, target in edges:
            if source == node and target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def score(edges, start=0):
    """Reachable states before and in the worst single-edge failure."""
    baseline = len(reachable(edges, start))
    worst = min(
        (len(reachable(edges[:i] + edges[i + 1:], start))
         for i in range(len(edges))),
        default=baseline,
    )
    return baseline, worst


def main():
    base = [(0, 1), (0, 2), (1, 3), (2, 3)]
    fragile = base + [(3, 4), (4, 5)]
    resilient = fragile + [(1, 4), (2, 5)]

    for name, edges in (
        ("baseline", base),
        ("fragile expansion", fragile),
        ("resilient expansion", resilient),
    ):
        observed, worst_case = score(edges)
        print(f"{name}: reachable={observed}, worst_one_edge_failure={worst_case}")

    assert score(base) == (4, 3)
    assert score(fragile) == (6, 4)
    assert score(resilient) == (6, 5)
    print("PASS: future-state count alone does not measure robust agency")


if __name__ == "__main__":
    main()
