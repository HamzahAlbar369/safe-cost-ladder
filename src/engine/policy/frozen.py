"""The frozen policy (SPEC §7.6, Phase 4): every choice O1 and the baselines make, derived ONCE from the dev
matrix and the frozen config/policy.yaml, then applied unchanged to shifted and held-out.

Nothing here reads shifted or held-out results: floors and budgets are policy.yaml (checked value for value
against the dev cells), the per-task static configs and the B1 / B4 configs are picked on dev, and the O1
options are the defaults approved in Phase 3 (D3.2, D3.5: haiku-low || haiku-medium, D = 6.0 s, opus-low).
"""

from __future__ import annotations

from engine.contracts import Frozen, Ticket
from engine.eval.baselines import (
    CellIndex,
    Chooser,
    best_config,
    cheapest_meeting_all_floors,
    index_cells,
    static_by_task,
)
from engine.eval.cells import build_cells
from engine.eval.data import load_split
from engine.eval.floors import Floors
from engine.policy.cascade import O1Options
from engine.policy.controller import floors_for, load_policy

DEV_RUN = "matrix-dev-full-1"
CHEAPEST = "haiku-low"


class FrozenChoices(Frozen):
    dev_run: str
    floors: Floors
    static: dict[str, str]  # per task, the cheapest config meeting the floor on dev (B3; O1 non-adjudicate)
    b1: str  # most accurate config on dev
    b4: str | None  # cheapest single config meeting every floor on dev
    o1: O1Options


def frozen_choices(dev_run: str = DEV_RUN) -> FrozenChoices:
    cells, problems = build_cells([dev_run], load_split("dev"))
    if problems:
        raise RuntimeError(f"{len(problems)} dev cells without a response, e.g. {problems[0]}")
    index = index_cells(cells)
    floors = floors_for(cells, load_policy())
    return FrozenChoices(
        dev_run=dev_run,
        floors=floors,
        static=static_by_task(index, floors),
        b1=best_config(index),
        b4=cheapest_meeting_all_floors(index, floors),
        o1=O1Options(),
    )


def frozen_baselines(fc: FrozenChoices, index: CellIndex) -> dict[str, Chooser]:
    """B1-B5 with the configs chosen on dev; `index` (any split) is read only to follow B5's V0 check."""
    b1, static = fc.b1, fc.static

    def b5(t: Ticket) -> tuple[str, ...]:
        return (CHEAPEST,) if index[(t.id, CHEAPEST)].parsed_ok else (CHEAPEST, b1)

    out: dict[str, Chooser] = {
        f"B1: always-best ({b1})": lambda t: (b1,),
        f"B2: always-cheapest ({CHEAPEST})": lambda t: (CHEAPEST,),
        "B3: best static config per task (chosen on dev)": lambda t: (static[t.task_type],),
        "B5: naive cascade (haiku-low -> B1 on V0 failure)": b5,
    }
    if fc.b4 is not None:
        b4 = fc.b4
        out[f"B4: cheapest single config meeting every floor on dev ({b4})"] = lambda t: (b4,)
    return dict(sorted(out.items()))
