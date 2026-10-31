"""Scenario switcher (SPEC §8, `engine scenario`): what-if analysis by replay over the recorded matrices.
Instant, no API calls.

A scenario changes the world, not the recordings:
- price multipliers per model (every cost component of that model scales; costs are linear in the prices);
- an outage removes every config of a model;
- latency budgets per task are overridden;
- accuracy floors move by a delta.

Declared adaptation rule (the controller re-applies the FROZEN selection rules on dev to the changed world; no
choice is ever made on the split being scored):
- static config per task = the cheapest (headline, dev, scenario prices) available config whose dev accuracy
  meets the (scenario) floor; if none does, the most accurate available config on dev;
- adjudicate keeps the O1 cascade (first || second -> top) if all three of its configs are available; if `top`
  is out, `top` becomes the most accurate available config on dev; if `first` or `second` is out, adjudicate
  uses its static config alone (no cascade); the second-opinion deadline D stays 6.0 s;
- B1 = the most accurate available config on dev.
"""

from __future__ import annotations

from collections.abc import Iterable

from engine.contracts import Frozen, Ticket
from engine.eval import bootstrap as B
from engine.eval.baselines import CellIndex, Outcome, index_cells, run_policy, summarize
from engine.eval.cells import Cell
from engine.eval.floors import Floors
from engine.eval.metrics import TASKS, mean
from engine.policy.cascade import O1Options, run_o1
from engine.policy.frozen import FrozenChoices


class Scenario(Frozen):
    name: str
    price: dict[str, float] = {}  # model short name (haiku|sonnet|opus) -> multiplier
    outage: tuple[str, ...] = ()  # model short names removed
    budget_s: dict[str, float] = {}  # task -> latency budget override (seconds)
    floor_delta: float = 0.0  # added to every per-task accuracy floor


BASELINE = Scenario(name="as recorded (no change)")
PRESETS: tuple[Scenario, ...] = (
    Scenario(name="Opus price 2x", price={"opus": 2.0}),
    Scenario(name="Haiku outage", outage=("haiku",)),
    Scenario(name="Tighter adjudicate budget (6.0 s)", budget_s={"adjudicate": 6.0}),
    Scenario(name="Floors 2 pts lower", floor_delta=-0.02),
)


def parse(name: str, price: Iterable[str] = (), outage: Iterable[str] = (), budget: Iterable[str] = (),
          floor_delta: float = 0.0) -> Scenario:  # fmt: skip
    """CLI form: --price opus=2x --outage haiku --budget adjudicate=6.0 --floor-delta -0.02"""

    def kv(items: Iterable[str]) -> dict[str, float]:
        out = {}
        for item in items:
            key, _, val = item.partition("=")
            out[key.strip()] = float(val.strip().rstrip("x"))
        return out

    return Scenario(
        name=name, price=kv(price), outage=tuple(outage), budget_s=kv(budget), floor_delta=floor_delta
    )


def _model(config_id: str) -> str:
    return config_id.split("-")[0]


def apply_cells(cells: list[Cell], sc: Scenario) -> list[Cell]:
    out = []
    for c in cells:
        m = _model(c.config_id)
        if m in sc.outage:
            continue
        k = sc.price.get(m, 1.0)
        out.append(
            c
            if k == 1.0
            else c.model_copy(update={"cost_usd": c.cost_usd * k, "cost_usd_nocache": c.cost_usd_nocache * k})
        )
    return out


def apply_floors(floors: Floors, sc: Scenario) -> Floors:
    return Floors(
        per_task={
            t: f.model_copy(
                update={
                    "floor": round(f.floor + sc.floor_delta, 6),
                    "budget_s": sc.budget_s.get(t, f.budget_s),
                }
            )
            for t, f in floors.per_task.items()
        }
    )


def _configs(index: CellIndex) -> list[str]:
    return sorted({cfg for _, cfg in index})


def _acc(index: CellIndex, cfg: str, task: str | None = None) -> float:
    return mean(c.correct for (_, k), c in index.items() if k == cfg and task in (None, c.task))


def _cost(index: CellIndex, cfg: str, task: str | None = None) -> float:
    return mean(c.cost_usd_nocache for (_, k), c in index.items() if k == cfg and task in (None, c.task))


def most_accurate(index: CellIndex, task: str | None = None) -> str:
    return min(_configs(index), key=lambda c: (-_acc(index, c, task), _cost(index, c, task)))


def pick_static(dev: CellIndex, floors: Floors) -> dict[str, str]:
    pick = {}
    for t in TASKS:
        ok = [c for c in _configs(dev) if _acc(dev, c, t) >= floors.per_task[t].floor]
        pick[t] = min(ok, key=lambda c: _cost(dev, c, t)) if ok else most_accurate(dev, t)
    return pick


class Adapted(Frozen):
    """The policy the controller runs in a scenario (all chosen on dev)."""

    floors: Floors
    static: dict[str, str]
    b1: str
    o1: O1Options | None  # None = adjudicate uses its static config alone (cascade unavailable)


def adapt(fc: FrozenChoices, dev_cells: list[Cell], sc: Scenario) -> Adapted:
    dev = index_cells(apply_cells(dev_cells, sc))
    floors = apply_floors(fc.floors, sc)
    static = pick_static(dev, floors)
    available = set(_configs(dev))
    o = fc.o1
    if o.first not in available or o.second not in available:
        o1 = None
    elif o.top not in available:
        o1 = o.model_copy(update={"top": most_accurate(dev, "adjudicate")})
    else:
        o1 = o
    return Adapted(floors=floors, static=static, b1=most_accurate(dev), o1=o1)


def run_adapted(a: Adapted, tickets: list[Ticket], index: CellIndex) -> list[Outcome]:
    if a.o1 is not None:
        outs, _ = run_o1(tickets, index, a.floors, a.static, a.o1)
        return outs
    by_id = {}
    other = [t for t in tickets if t.task_type != "adjudicate"]
    for o in run_o1(other, index, a.floors, a.static, O1Options())[0]:
        by_id[o.ticket_id] = o
    adj = [t for t in tickets if t.task_type == "adjudicate"]
    for o in run_policy(lambda t: (a.static["adjudicate"],), adj, index, a.floors):
        by_id[o.ticket_id] = o
    return [by_id[t.id] for t in tickets]


class ScenarioResult(Frozen):
    scenario: Scenario
    adapted: Adapted
    o1: list[Outcome]
    b1: list[Outcome]


def evaluate(
    fc: FrozenChoices, dev_cells: list[Cell], cells: list[Cell], tickets: list[Ticket], sc: Scenario
) -> ScenarioResult:
    a = adapt(fc, dev_cells, sc)
    index = index_cells(apply_cells(cells, sc))
    b1 = run_policy(lambda t: (a.b1,), tickets, index, a.floors)
    return ScenarioResult(scenario=sc, adapted=a, o1=run_adapted(a, tickets, index), b1=b1)


def _meets(outs: list[Outcome], floors: Floors) -> bool:
    return all(
        summarize([o for o in outs if o.task == t])["accuracy"] >= floors.per_task[t].floor for t in TASKS
    )


def format_result(r: ScenarioResult, base: ScenarioResult) -> list[str]:
    a, s, sb = r.adapted, summarize(r.o1), summarize(base.o1)
    samples = B.resample_indices(len(r.o1))
    cascade = (
        f"{a.o1.first} || {a.o1.second} -> {a.o1.top}"
        if a.o1 is not None
        else f"cascade unavailable: {a.static['adjudicate']} alone"
    )
    lines = [
        f"Scenario: {r.scenario.name}",
        f"    change: price {r.scenario.price or '-'} | outage {list(r.scenario.outage) or '-'} | "
        f"budgets {r.scenario.budget_s or '-'} | floor delta {r.scenario.floor_delta:+.2f}",
        "    controller picks (on dev): "
        + ", ".join(f"{t} {c}" for t, c in a.static.items() if t != "adjudicate")
        + f"; adjudicate {cascade}; B1 {a.b1}",
    ]
    for key, field, label in (
        ("cost_nocache", "cpst_nocache", "headline"),
        ("cost_cached", "cpst_cached", "with caching"),
    ):
        arr = ([getattr(o, key) for o in r.o1], [float(o.success) for o in r.o1])
        ref = ([getattr(o, key) for o in r.b1], [float(o.success) for o in r.b1])
        lo, hi = B.cpst_ci(*arr, samples)
        b1 = summarize(r.b1)[field]
        glo, ghi = B.paired_diff_ci(ref, arr, samples, relative=True)
        lines.append(
            f"    O1 CPST {label:<13} ${s[field]:.5f} [{lo:.5f}, {hi:.5f}] (as recorded ${sb[field]:.5f}); "
            f"vs B1 ${b1:.5f}: saving {(b1 - s[field]) / b1:+.1%} [{glo:+.1%}, {ghi:+.1%}]"
        )
    lines.append(
        f"    O1 accuracy {s['accuracy']:.3f} (as recorded {sb['accuracy']:.3f})  "
        f"success {s['success_rate']:.3f} (as recorded {sb['success_rate']:.3f})  p95 {s['p95_s']:.2f}s  "
        f"meets every (scenario) floor: {'yes' if _meets(r.o1, a.floors) else 'NO'}"
    )
    per = []
    for t in TASKS:
        sub = summarize([o for o in r.o1 if o.task == t])
        per.append(f"{t} acc {sub['accuracy']:.3f} succ {sub['success_rate']:.3f}")
    lines.append("    per task: " + " | ".join(per))
    return lines


RUNS = {"dev": "matrix-dev-full-1", "shifted": "matrix-shifted-full-1"}


def report(scenarios: Iterable[Scenario] = PRESETS, splits: Iterable[str] = ("dev", "shifted")) -> str:
    """Every scenario on every split, each against the same policy as recorded (BASELINE)."""
    from engine.eval.cells import build_cells
    from engine.eval.data import load_split
    from engine.policy.frozen import frozen_choices

    fc = frozen_choices()
    dev_tickets = sorted(load_split("dev"), key=lambda t: t.id)
    dev_cells, _ = build_cells([RUNS["dev"]], dev_tickets)
    scenarios = list(scenarios)
    lines = [
        "Scenario switcher (SPEC 8): replay over the recorded matrices, no API calls. The controller",
        "re-applies the frozen selection rules ON DEV to the changed world (src/engine/eval/scenarios.py",
        "docstring); the split being scored is never used to choose. 'as recorded' = the frozen O1 with no",
        "change. CIs: 95% bootstrap. Floors and budgets in each line are the scenario's.",
    ]
    for split in splits:
        if split == "dev":
            tickets, cells = dev_tickets, dev_cells
        else:
            tickets = sorted(load_split(split), key=lambda t: t.id)
            cells, _ = build_cells([RUNS[split]], tickets)
        base = evaluate(fc, dev_cells, cells, tickets, BASELINE)
        lines += ["", f"=== split {split} (run {RUNS[split]}, n={len(tickets)})"]
        for sc in scenarios:
            lines += ["", *format_result(evaluate(fc, dev_cells, cells, tickets, sc), base)]
    return "\n".join(lines)
