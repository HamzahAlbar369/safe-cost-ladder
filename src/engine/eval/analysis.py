"""Phase 2 analysis over recorded cells: baselines B1-B5 with bootstrap CIs, oracle and oracle gap, Pareto
ladder per task, and the router go/no-go headroom (SPEC §7.3, §7.5, §7.7). Replay only; no API calls."""

from __future__ import annotations

from collections import Counter

from engine.contracts import Frozen, Ticket
from engine.eval import bootstrap as B
from engine.eval.baselines import (
    CellIndex,
    Outcome,
    baselines,
    index_cells,
    oracle,
    run_policy,
    summarize,
)
from engine.eval.cells import Cell
from engine.eval.floors import Floors, config_stats
from engine.eval.metrics import TASKS

ROUTER_MIN_CPST_GAIN = 0.05  # SPEC §7.7(a): a router must improve CPST by >= 5% to be kept


class LadderRung(Frozen):
    config: str
    accuracy: float
    mean_cost_nocache: float
    p95_s: float


def pareto_ladder(cells: list[Cell], task: str) -> tuple[list[LadderRung], list[str]]:
    """Configs on the accuracy/cost frontier for a task, cheapest first, and the dominated ones removed
    (another config is at least as accurate AND at least as cheap, and strictly better on one)."""
    stats = config_stats(cells, task)
    keep, dropped = [], []
    for s in stats:
        dominated = any(
            o.accuracy >= s.accuracy
            and o.mean_cost_nocache <= s.mean_cost_nocache
            and (o.accuracy > s.accuracy or o.mean_cost_nocache < s.mean_cost_nocache)
            for o in stats
        )
        (dropped if dominated else keep).append(s)
    ladder = [LadderRung(**s.model_dump()) for s in sorted(keep, key=lambda s: s.mean_cost_nocache)]
    return ladder, [s.config for s in dropped]


class PolicyRow(Frozen):
    name: str
    summary: dict[str, float]
    cpst_nocache_ci: tuple[float, float]
    cpst_cached_ci: tuple[float, float]
    gain_vs_b1_nocache: float  # relative CPST reduction vs B1 (positive = cheaper)
    gain_vs_b1_ci: tuple[float, float]
    gap_captured: float | None  # (CPST_B1 - CPST_p) / (CPST_B1 - CPST_oracle), headline basis
    meets_floors: (
        bool  # accuracy >= the per-task floor on every task (CPST alone can reward failing hard tasks)
    )


class Analysis(Frozen):
    rows: list[PolicyRow]
    per_task: dict[str, dict[str, dict[str, float]]]  # policy -> task -> summary
    per_language: dict[str, dict[str, dict[str, float]]]
    ladders: dict[str, list[LadderRung]]
    dominated: dict[str, list[str]]
    oracle_choice_counts: dict[str, dict[str, int]]  # task -> config -> tickets the oracle sends there
    headroom: dict[str, float | bool | str]


def _arrays(outcomes: list[Outcome]) -> dict[str, list[float]]:
    return {
        "nocache": [o.cost_nocache for o in outcomes],
        "cached": [o.cost_cached for o in outcomes],
        "success": [float(o.success) for o in outcomes],
    }


def analyse(cells: list[Cell], tickets: list[Ticket], floors: Floors) -> Analysis:
    index: CellIndex = index_cells(cells)
    tickets = sorted((t for t in tickets if (t.id, "haiku-low") in index), key=lambda t: t.id)
    choosers = baselines(index, floors)
    choosers["Oracle: cheapest correct config within budget, per ticket"] = oracle(index, floors)
    outcomes = {name: run_policy(ch, tickets, index, floors) for name, ch in choosers.items()}
    samples = B.resample_indices(len(tickets))
    arr = {name: _arrays(o) for name, o in outcomes.items()}

    b1_name = next(n for n in outcomes if n.startswith("B1"))
    oracle_name = next(n for n in outcomes if n.startswith("Oracle"))
    b1, orc = summarize(outcomes[b1_name])["cpst_nocache"], summarize(outcomes[oracle_name])["cpst_nocache"]
    rows = []
    for name, outs in outcomes.items():
        s, a = summarize(outs), arr[name]
        gain_ci = B.paired_diff_ci(
            (arr[b1_name]["nocache"], arr[b1_name]["success"]),
            (a["nocache"], a["success"]),
            samples,
            relative=True,
        )
        captured = (b1 - s["cpst_nocache"]) / (b1 - orc) if b1 > orc else None
        meets = all(
            summarize([o for o in outs if o.task == t])["accuracy"] >= floors.per_task[t].floor for t in TASKS
        )
        rows.append(
            PolicyRow(
                name=name,
                summary=s,
                cpst_nocache_ci=B.cpst_ci(a["nocache"], a["success"], samples),
                cpst_cached_ci=B.cpst_ci(a["cached"], a["success"], samples),
                gain_vs_b1_nocache=(b1 - s["cpst_nocache"]) / b1,
                gain_vs_b1_ci=gain_ci,
                gap_captured=captured,
                meets_floors=meets,
            )
        )

    ladders, dominated = {}, {}
    for task in TASKS:
        ladders[task], dominated[task] = pareto_ladder(cells, task)
    picks: dict[str, Counter[str]] = {t: Counter() for t in TASKS}
    for o in outcomes[oracle_name]:
        picks[o.task][o.path[0]] += 1
    return Analysis(
        rows=rows,
        per_task={
            n: {t: summarize([o for o in outs if o.task == t]) for t in TASKS} for n, outs in outcomes.items()
        },
        per_language={
            n: {lg: summarize([o for o in outs if o.language == lg]) for lg in ("en", "ar")}
            for n, outs in outcomes.items()
        },
        ladders=ladders,
        dominated=dominated,
        oracle_choice_counts={t: dict(c.most_common()) for t, c in picks.items()},
        headroom=router_headroom(rows, oracle_name),
    )


def router_headroom(rows: list[PolicyRow], oracle_name: str) -> dict[str, float | bool | str]:
    """Go/no-go for building routers (SPEC §7.7). A router can at best reach the oracle, so if even the
    oracle is not >= 5% cheaper per successful task than the best non-router policy, no router can pass the
    keep rule on CPST. In Phase 2 the non-router set is the B1-B5 policies that meet every accuracy floor;
    the Phase 3 cascade (O1) will narrow this."""
    by_name = {r.name: r for r in rows}
    non_router = [r for r in rows if r.name != oracle_name and r.meets_floors]
    best = min(non_router, key=lambda r: r.summary["cpst_nocache"])
    headroom = (best.summary["cpst_nocache"] - by_name[oracle_name].summary["cpst_nocache"]) / best.summary[
        "cpst_nocache"
    ]
    return {
        "best_non_router": best.name,
        "best_non_router_cpst_nocache": best.summary["cpst_nocache"],
        "oracle_cpst_nocache": by_name[oracle_name].summary["cpst_nocache"],
        "headroom_cpst": headroom,
        "threshold": ROUTER_MIN_CPST_GAIN,
        "go": headroom >= ROUTER_MIN_CPST_GAIN,
    }
