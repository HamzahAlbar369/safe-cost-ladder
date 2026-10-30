"""Policies evaluated by lookup over recorded cells (SPEC §7.3, §7.4): baselines B1-B5 and the oracle.

A policy is a rule that picks a path of configs per ticket; its cost and latency are the sums over the path's
recorded cells and its answer is the last cell's. A task succeeds iff the final answer is correct AND the
summed latency is within that task's budget (SPEC §7.1). No API calls.
"""

from __future__ import annotations

from collections.abc import Callable

from engine.contracts import Frozen, Ticket
from engine.eval.cells import Cell
from engine.eval.floors import Floors
from engine.eval.metrics import TASKS, mean, percentile

CellIndex = dict[tuple[str, str], Cell]
Chooser = Callable[[Ticket], tuple[str, ...]]  # ticket -> path of config ids (cascade order)

B3_LABEL = "B3: best static config per task (tuned on dev)"


class Outcome(Frozen):
    ticket_id: str
    task: str
    language: str
    path: tuple[str, ...]
    correct: bool
    success: bool  # correct AND within the task's latency budget
    cost_nocache: float  # Cost without caching (headline)
    cost_cached: float  # Cost with caching (actual)
    latency_ms: float  # summed over the path; request sent -> response received


def index_cells(cells: list[Cell]) -> CellIndex:
    return {(c.ticket_id, c.config_id): c for c in cells}


def run_policy(chooser: Chooser, tickets: list[Ticket], index: CellIndex, floors: Floors) -> list[Outcome]:
    outcomes = []
    for t in tickets:
        path = chooser(t)
        cells = [index[(t.id, cfg)] for cfg in path]
        latency = sum(c.latency_ms for c in cells)
        correct = cells[-1].correct
        outcomes.append(
            Outcome(
                ticket_id=t.id,
                task=t.task_type,
                language=t.language,
                path=path,
                correct=correct,
                success=correct and latency <= floors.per_task[t.task_type].budget_s * 1000,
                cost_nocache=sum(c.cost_usd_nocache for c in cells),
                cost_cached=sum(c.cost_usd for c in cells),
                latency_ms=latency,
            )
        )
    return outcomes


def summarize(outcomes: list[Outcome]) -> dict[str, float]:
    wins = sum(o.success for o in outcomes)
    nocache, cached = sum(o.cost_nocache for o in outcomes), sum(o.cost_cached for o in outcomes)
    lat = [o.latency_ms for o in outcomes]
    inf = float("inf")
    return {
        "n": len(outcomes),
        "accuracy": mean(o.correct for o in outcomes),
        "success_rate": wins / len(outcomes) if outcomes else 0.0,
        "cpst_nocache": nocache / wins if wins else inf,
        "cpst_cached": cached / wins if wins else inf,
        "usd_nocache": nocache,
        "usd_cached": cached,
        "p50_s": percentile(lat, 50) / 1000,
        "p95_s": percentile(lat, 95) / 1000,
    }


# --- choosers -------------------------------------------------------------------------------------


def accuracy_of(index: CellIndex, config: str, task: str | None = None) -> float:
    return mean(c.correct for (tid, cfg), c in index.items() if cfg == config and (task in (None, c.task)))


def mean_cost(index: CellIndex, config: str, task: str | None = None) -> float:
    return mean(
        c.cost_usd_nocache for c in index.values() if c.config_id == config and task in (None, c.task)
    )


def config_ids(index: CellIndex) -> list[str]:
    return sorted({cfg for _, cfg in index})


def best_config(index: CellIndex) -> str:
    """B1: the most accurate config overall; ties go to the lower headline cost."""
    return min(config_ids(index), key=lambda c: (-accuracy_of(index, c), mean_cost(index, c)))


def static_by_task(index: CellIndex, floors: Floors) -> dict[str, str]:
    """B3: per task, the cheapest (headline) config whose dev accuracy meets that task's floor."""
    pick = {}
    for task in TASKS:
        ok = [c for c in config_ids(index) if accuracy_of(index, c, task) >= floors.per_task[task].floor]
        pick[task] = min(ok, key=lambda c: mean_cost(index, c, task))
    return pick


def cheapest_meeting_all_floors(index: CellIndex, floors: Floors) -> str | None:
    """B4: the cheapest single config (headline) that meets every task floor, or None."""
    ok = [
        c
        for c in config_ids(index)
        if all(accuracy_of(index, c, t) >= floors.per_task[t].floor for t in TASKS)
    ]
    return min(ok, key=lambda c: mean_cost(index, c)) if ok else None


def baselines(index: CellIndex, floors: Floors) -> dict[str, Chooser]:
    b1 = best_config(index)
    b3 = static_by_task(index, floors)
    b4 = cheapest_meeting_all_floors(index, floors)
    cheapest = "haiku-low"

    def b5(t: Ticket) -> tuple[str, ...]:
        first = index[(t.id, cheapest)]
        return (cheapest,) if first.parsed_ok else (cheapest, b1)  # escalate on a V0 failure only

    out: dict[str, Chooser] = {
        f"B1: always-best ({b1})": lambda t: (b1,),
        f"B2: always-cheapest ({cheapest})": lambda t: (cheapest,),
        B3_LABEL: lambda t: (b3[t.task_type],),
        "B5: naive cascade (haiku-low -> best on V0 failure)": b5,
    }
    if b4 is not None:
        out[f"B4: cheapest single config meeting every floor ({b4})"] = lambda t: (b4,)
    return dict(sorted(out.items()))


def oracle(index: CellIndex, floors: Floors) -> Chooser:
    """Per ticket, the cheapest (headline) config that is correct within the task budget. A ticket no config
    solves in budget is charged the cheapest config and counts as a failure."""
    configs = config_ids(index)
    cheapest = min(configs, key=lambda c: mean_cost(index, c))

    def choose(t: Ticket) -> tuple[str, ...]:
        budget_ms = floors.per_task[t.task_type].budget_s * 1000
        good = [c for c in configs if index[(t.id, c)].correct and index[(t.id, c)].latency_ms <= budget_ms]
        return (min(good, key=lambda c: index[(t.id, c)].cost_usd_nocache),) if good else (cheapest,)

    return choose
