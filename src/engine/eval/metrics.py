"""Pure summaries of matrix cells: accuracy, parse rate, cost, latency, per config / task / language."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable

from engine.eval.cells import Cell

TASKS = ("faq", "intent", "extract", "adjudicate")


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile (q in 0-100); 0.0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q / 100 * len(ordered)) - 1)]


def mean(values: Iterable[float]) -> float:
    vals = list(values)
    return sum(vals) / len(vals) if vals else 0.0


def group(cells: Iterable[Cell], key: Callable[[Cell], tuple]) -> dict[tuple, list[Cell]]:
    out: dict[tuple, list[Cell]] = defaultdict(list)
    for c in cells:
        out[key(c)].append(c)
    return dict(out)


def accuracy(cells: list[Cell]) -> float:
    return mean(c.correct for c in cells)


def parse_rate(cells: list[Cell]) -> float:
    return mean(c.parsed_ok for c in cells)


def latency_stats(cells: list[Cell]) -> dict[str, float]:
    """Seconds, request sent -> response received (queue wait excluded)."""
    ms = [c.latency_ms for c in cells]
    return {"p50": percentile(ms, 50) / 1000, "p95": percentile(ms, 95) / 1000, "mean": mean(ms) / 1000}


def cost_stats(cells: list[Cell]) -> dict[str, float]:
    return {
        "with_caching": sum(c.cost_usd for c in cells),  # "Cost with caching (actual)"
        "without_caching": sum(c.cost_usd_nocache for c in cells),  # "Cost without caching (headline)"
    }


def config_table(cells: list[Cell]) -> list[dict]:
    """One row per config (overall): n, accuracy, parse rate, truncations, latency, cost."""
    rows = []
    for (config_id,), cs in sorted(group(cells, lambda c: (c.config_id,)).items()):
        lat, cost = latency_stats(cs), cost_stats(cs)
        rows.append(
            {
                "config": config_id,
                "n": len(cs),
                "accuracy": accuracy(cs),
                "parse_rate": parse_rate(cs),
                "truncated": sum(c.truncated for c in cs),
                "p50_s": lat["p50"],
                "p95_s": lat["p95"],
                "queue_wait_p95_s": percentile([c.queue_wait_ms for c in cs], 95) / 1000,
                "out_tokens_mean": mean(c.output_tokens for c in cs),
                "usd_cached": cost["with_caching"],
                "usd_nocache": cost["without_caching"],
            }
        )
    return rows


def accuracy_matrix(cells: list[Cell]) -> dict[str, dict[str, tuple[float, int]]]:
    """config -> task -> (accuracy, n)."""
    out: dict[str, dict[str, tuple[float, int]]] = defaultdict(dict)
    for (config_id, task), cs in group(cells, lambda c: (c.config_id, c.task)).items():
        out[config_id][task] = (accuracy(cs), len(cs))
    return dict(out)
