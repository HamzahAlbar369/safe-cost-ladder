"""Controller: reads the frozen config/policy.yaml (SPEC §6.1 step 5) and refuses anything not frozen.

Floors and budgets are never re-tuned in Phase 3. `floors_for` re-derives the full `Floors` object from the
recorded dev cells with the frozen budget rule and checks it matches policy.yaml value for value, so the
evaluation cannot silently drift from what was tagged `floors-v1`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from engine.contracts import Frozen
from engine.eval.cells import Cell
from engine.eval.floors import POLICY_YAML, Floors, derive_floors
from engine.eval.metrics import TASKS


class PolicyConfig(Frozen):
    status: str
    budget_rule: str
    floors: dict[str, float]
    latency_budget_s: dict[str, float]
    cost_of_error_usd: dict[str, float]
    retry_budget: int


class NotFrozen(RuntimeError):
    pass


def load_policy(path: Path = POLICY_YAML) -> PolicyConfig:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    cfg = PolicyConfig(
        status=doc["status"],
        budget_rule=doc["budget_rule"],
        floors={t: v["accuracy"] for t, v in doc["floors"].items()},
        latency_budget_s=doc["latency_budget_s"],
        cost_of_error_usd=doc["cost_of_error_usd"],
        retry_budget=doc["retry_budget"],
    )
    if cfg.status != "frozen":
        raise NotFrozen(f"{path.name} status is {cfg.status!r}; Phase 3 needs the frozen floors-v1 policy")
    return cfg


def floors_for(cells: list[Cell], cfg: PolicyConfig) -> Floors:
    floors = derive_floors(cells, cfg.budget_rule)
    for t in TASKS:
        f = floors.per_task[t]
        if round(f.floor, 6) != cfg.floors[t] or f.budget_s != cfg.latency_budget_s[t]:
            raise ValueError(f"{t}: cells give floor {f.floor} / budget {f.budget_s}s, policy.yaml differs")
    return floors
