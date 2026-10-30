"""Deterministic stratified subsets of a split (the Phase 2 pilot)."""

from __future__ import annotations

import random
from collections import defaultdict

from engine.contracts import Ticket

PILOT_SEED = 20261030
PILOT_SIZE = 40
ARABIC_SHARE = 0.3


def _quotas(sizes: dict[tuple[str, str], int], total: int) -> dict[tuple[str, str], int]:
    """Largest-remainder allocation of `total` over (task, level) strata, at least 1 per stratum."""
    n = sum(sizes.values())
    exact = {k: total * v / n for k, v in sizes.items()}
    quota = {k: max(1, int(x)) for k, x in exact.items()}
    by_remainder = sorted(exact, key=lambda k: exact[k] - int(exact[k]), reverse=True)
    i = 0
    while sum(quota.values()) < total:
        quota[by_remainder[i % len(by_remainder)]] += 1
        i += 1
    while sum(quota.values()) > total:
        biggest = max(quota, key=lambda k: quota[k])
        quota[biggest] -= 1
    return quota


def stratified_subset(tickets: list[Ticket], size: int = PILOT_SIZE, seed: int = PILOT_SEED) -> list[Ticket]:
    """`size` tickets stratified by task x level, each stratum ~30% Arabic, same ids on every call."""
    strata: dict[tuple[str, str], list[Ticket]] = defaultdict(list)
    for t in tickets:
        strata[(t.task_type, t.level)].append(t)
    quota = _quotas({k: len(v) for k, v in strata.items()}, size)
    picked: list[Ticket] = []
    for key in sorted(strata):
        rng = random.Random(f"{seed}:{key[0]}:{key[1]}")
        ar = [t for t in strata[key] if t.language == "ar"]
        en = [t for t in strata[key] if t.language == "en"]
        n_ar = min(len(ar), round(quota[key] * ARABIC_SHARE))
        n_en = min(len(en), quota[key] - n_ar)
        picked += rng.sample(ar, n_ar) + rng.sample(en, n_en)
    return sorted(picked, key=lambda t: t.id)
