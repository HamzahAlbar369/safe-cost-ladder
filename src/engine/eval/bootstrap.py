"""Paired bootstrap over tickets (SPEC §7.5): 2,000 resamples, fixed seed, 95% percentile intervals.

The same resampled ticket indices are used for every policy, so differences between policies are paired.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

RESAMPLES = 2000
SEED = 20261030


def resample_indices(n: int, resamples: int = RESAMPLES, seed: int = SEED) -> list[list[int]]:
    rng = random.Random(seed)
    return [[rng.randrange(n) for _ in range(n)] for _ in range(resamples)]


def percentile_ci(samples: list[float], level: float = 0.95) -> tuple[float, float]:
    ordered = sorted(samples)
    lo = ordered[int((1 - level) / 2 * (len(ordered) - 1))]
    hi = ordered[int((1 + level) / 2 * (len(ordered) - 1))]
    return lo, hi


def ratio_of_sums(cost: Sequence[float], success: Sequence[float], idx: list[int]) -> float:
    """CPST on a resample: total cost / number of successes (infinite if none)."""
    wins = sum(success[i] for i in idx)
    return sum(cost[i] for i in idx) / wins if wins else float("inf")


def cpst_ci(cost: Sequence[float], success: Sequence[float], samples: list[list[int]]) -> tuple[float, float]:
    return percentile_ci([ratio_of_sums(cost, success, idx) for idx in samples])


def paired_diff_ci(
    base: tuple[Sequence[float], Sequence[float]],
    other: tuple[Sequence[float], Sequence[float]],
    samples: list[list[int]],
    *,
    relative: bool = False,
) -> tuple[float, float]:
    """CI of CPST(base) - CPST(other), or of that difference as a share of CPST(base) when `relative`
    (positive = `other` is cheaper per successful task)."""
    diffs = []
    for idx in samples:
        a, b = ratio_of_sums(*base, idx), ratio_of_sums(*other, idx)
        if a == float("inf") or b == float("inf"):
            continue
        diffs.append((a - b) / a if relative else a - b)
    return percentile_ci(diffs)


def mean_ci(values: Sequence[float], samples: list[list[int]]) -> tuple[float, float]:
    return percentile_ci([sum(values[i] for i in idx) / len(idx) for idx in samples])


def paired_mean_diff_ci(
    a: Sequence[float], b: Sequence[float], samples: list[list[int]]
) -> tuple[float, float]:
    return percentile_ci([sum(a[i] - b[i] for i in idx) / len(idx) for idx in samples])
