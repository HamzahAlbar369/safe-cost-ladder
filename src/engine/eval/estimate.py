"""Pre-run cost and wall-clock estimates (CLAUDE.md: every paid command prints one first).

Labels follow SPEC §7.5: "Cost with caching (actual)" and "Cost without caching (headline)".
Input tokens: the expected figure assumes ~4 UTF-8 bytes/token on the English-heavy static prefix and 2
bytes/token on the (partly Arabic) ticket; the worst case uses 2 bytes/token everywhere. Output tokens
(thinking included) are an ASSUMPTION per task and effort until the pilot measures them; the worst case
is every call hitting max_tokens.
"""

from __future__ import annotations

import math
from collections import defaultdict

from pydantic import BaseModel

from engine.contracts import LLMRequest, TaskType
from engine.llm.client import estimate_tokens, worst_case_cost
from engine.llm.pricing import PER_MTOK, PriceBook, pricebook

EXPECTED_OUT_BY_TASK: dict[str, int] = {"faq": 80, "intent": 80, "extract": 200, "adjudicate": 500}
EFFORT_OUT_FACTOR = {"low": 1.0, "medium": 1.3, "high": 1.6}
EXPECTED_LATENCY_S = {"faq": 2.0, "intent": 2.0, "extract": 3.0, "adjudicate": 6.0}  # per call, assumption


class Estimate(BaseModel):
    calls: int
    cost_with_caching: float  # "Cost with caching (actual)"
    cost_without_caching: float  # "Cost without caching (headline)"
    worst_case: float
    wall_clock_s: float
    per_model: dict[str, float]  # expected cost with caching, by model
    assumptions: dict[str, str]


def expected_output_tokens(task: TaskType, effort: str) -> int:
    return round(EXPECTED_OUT_BY_TASK[task] * EFFORT_OUT_FACTOR[effort])


def estimate_requests(
    items: list[tuple[TaskType, LLMRequest]], *, concurrency: int, prices: PriceBook | None = None
) -> Estimate:
    prices = prices or pricebook()
    warmed: set[str] = set()
    with_cache = no_cache = worst = 0.0
    per_model: dict[str, float] = defaultdict(float)
    seconds = 0.0
    for task, req in items:
        p = prices.price(req.model)
        prefix = math.ceil(len(req.system.encode("utf-8")) / 4)
        user = estimate_tokens(req.user)
        out = expected_output_tokens(task, req.effort) * p.output
        write = req.model not in warmed
        warmed.add(req.model)
        c = (prefix * (p.cache_write_5m if write else p.cache_read) + user * p.input + out) / PER_MTOK
        with_cache += c
        no_cache += ((prefix + user) * p.input + out) / PER_MTOK
        per_model[req.model] += c
        worst += worst_case_cost(p, req)
        seconds += EXPECTED_LATENCY_S[task] * EFFORT_OUT_FACTOR[req.effort] ** 0.5
    return Estimate(
        calls=len(items),
        cost_with_caching=with_cache,
        cost_without_caching=no_cache,
        worst_case=worst,
        wall_clock_s=seconds / max(concurrency, 1),
        per_model=dict(per_model),
        assumptions={
            "input_tokens": "static prefix ~4 bytes/token, ticket 2 bytes/token (worst case: 2 bytes/token)",
            "output_tokens": f"assumed {EXPECTED_OUT_BY_TASK} x effort {EFFORT_OUT_FACTOR} (incl. thinking)",
            "cache": "one cache write per model, every other call reads (D0.6; TTL expiry ignored)",
            "latency": f"assumed {EXPECTED_LATENCY_S} s/call, divided by concurrency {concurrency}",
            "worst": "no cache reads, every call hits max_tokens",
        },
    )


def format_estimate(label: str, e: Estimate, remaining_usd: float) -> str:
    lines = [
        f"{label}: {e.calls} calls",
        f"  Cost with caching (actual):        ${e.cost_with_caching:>9.4f}",
        f"  Cost without caching (headline):   ${e.cost_without_caching:>9.4f}",
        f"  Worst case (all max_tokens):       ${e.worst_case:>9.4f}",
        f"  Wall clock (concurrency-adjusted): ~{e.wall_clock_s / 60:.1f} min",
        f"  Ledger remaining (anthropic):      ${remaining_usd:>9.4f}",
    ]
    lines += [f"  by model, with caching: {m} ${v:.4f}" for m, v in e.per_model.items()]
    lines += [f"  assumption {k}: {v}" for k, v in e.assumptions.items()]
    return "\n".join(lines)
