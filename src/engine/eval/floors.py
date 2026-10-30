"""Accuracy floors and latency budgets per task (SPEC §7.2), derived from dev baselines.

floor  = accuracy of the most accurate single config on dev for that task, minus a tolerance
         (adjudicate 1 pt; extract, intent, faq 2 pts). Ties for "most accurate" go to the lower
         Cost without caching (headline) (Hamzah).
budget = p95 latency of that same config on dev, rounded up to 0.5 s ("never slower than always-premium").
"""

from __future__ import annotations

import math
from pathlib import Path

import yaml

from engine.contracts import Frozen
from engine.eval.cells import Cell
from engine.eval.metrics import TASKS, group, mean, percentile
from engine.llm.pricing import ROOT

TOLERANCE = {"adjudicate": 0.01, "extract": 0.02, "intent": 0.02, "faq": 0.02}
COST_OF_ERROR_USD = {"faq": 0.5, "intent": 0.5, "extract": 5.0, "adjudicate": 50.0}  # SPEC §3.1
RETRY_BUDGET = 1  # SPEC §8: API errors retried at most once per call
POLICY_YAML = ROOT / "config" / "policy.yaml"


class ConfigStat(Frozen):
    config: str
    accuracy: float
    mean_cost_nocache: float
    p95_s: float


class TaskFloor(Frozen):
    task: str
    n: int
    best_config: str
    best_accuracy: float
    tolerance: float
    floor: float
    budget_config: str  # the config whose p95 sets the budget (see derive_floors)
    p95_s: float  # p95 of budget_config
    budget_s: float
    tied_best: tuple[ConfigStat, ...]  # every config sharing the top accuracy (for review)


class Floors(Frozen):
    per_task: dict[str, TaskFloor]


def round_up_half_second(seconds: float) -> float:
    return math.ceil(seconds * 2 - 1e-9) / 2


def config_stats(cells: list[Cell], task: str) -> list[ConfigStat]:
    out = []
    for (config,), cs in group([c for c in cells if c.task == task], lambda c: (c.config_id,)).items():
        out.append(
            ConfigStat(
                config=config,
                accuracy=mean(c.correct for c in cs),
                mean_cost_nocache=mean(c.cost_usd_nocache for c in cs),
                p95_s=percentile([c.latency_ms for c in cs], 95) / 1000,
            )
        )
    return sorted(out, key=lambda s: (-s.accuracy, s.mean_cost_nocache))


def derive_floors(cells: list[Cell], budget_rule: str = "cheapest") -> Floors:
    """`budget_rule` decides which config's p95 sets the latency budget when several configs tie for the top
    accuracy: "cheapest" (the approved tie-break: lower headline cost) or "premium" (the most expensive tied
    config, i.e. "never slower than always-premium")."""
    per_task = {}
    for task in TASKS:
        stats = config_stats(cells, task)
        best = stats[0]  # highest accuracy, then lowest headline cost
        tied = tuple(s for s in stats if s.accuracy == best.accuracy)
        ref = max(tied, key=lambda s: s.mean_cost_nocache) if budget_rule == "premium" else best
        per_task[task] = TaskFloor(
            task=task,
            n=sum(1 for c in cells if c.task == task and c.config_id == best.config),
            best_config=best.config,
            best_accuracy=best.accuracy,
            tolerance=TOLERANCE[task],
            floor=round(best.accuracy - TOLERANCE[task], 6),
            budget_config=ref.config,
            p95_s=ref.p95_s,
            budget_s=round_up_half_second(ref.p95_s),
            tied_best=tied,
        )
    return Floors(per_task=per_task)


def write_policy_yaml(
    floors: Floors,
    run_ids: list[str],
    git_sha: str,
    path: Path = POLICY_YAML,
    *,
    budget_rule: str = "cheapest",
    frozen: bool = False,
) -> None:
    doc = {
        # "frozen" only with Hamzah's sign-off, committed before any optimisation and tagged floors-v1
        "status": "frozen" if frozen else "proposed",
        "derived_from": {"runs": run_ids, "git_sha": git_sha, "split": "dev"},
        "budget_rule": budget_rule,
        "floors": {
            t: {"accuracy": f.floor, "best_config": f.best_config} for t, f in floors.per_task.items()
        },
        "latency_budget_s": {t: f.budget_s for t, f in floors.per_task.items()},
        "latency_budget_config": {t: f.budget_config for t, f in floors.per_task.items()},
        "cost_of_error_usd": COST_OF_ERROR_USD,
        "retry_budget": RETRY_BUDGET,
    }
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
