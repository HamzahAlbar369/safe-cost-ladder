"""The committed dev matrix must replay exactly from its cassettes with no key (Phase 2 gate)."""

import pytest

from engine.eval import replay
from engine.eval.data import load_split
from engine.llm.pricing import ROOT

RUN = "matrix-dev-full-1"


@pytest.mark.skipif(not (ROOT / "runs" / RUN / "calls.jsonl").exists(), reason="dev matrix not recorded")
def test_dev_matrix_replays_exactly_and_covers_every_cell():
    tickets = load_split("dev")
    assert replay.compare(RUN, tickets, repeat=1) == []
    from engine.eval.cells import build_cells

    cells, problems = build_cells([RUN], tickets)
    assert problems == [] and len(cells) == len(tickets) * 9


def test_frozen_policy_yaml_matches_the_floors_derived_from_the_committed_matrix():
    """Once config/policy.yaml is frozen (floors-v1) it must stay exactly what the dev matrix gives under the
    premium budget rule; changing floors or budgets needs a new decision, not a quiet edit."""
    import yaml

    from engine.eval.cells import build_cells
    from engine.eval.floors import derive_floors

    doc = yaml.safe_load((ROOT / "config" / "policy.yaml").read_text(encoding="utf-8"))
    if doc["status"] != "frozen":
        pytest.skip("floors not frozen yet")
    cells, _ = build_cells([RUN], load_split("dev"))
    derived = derive_floors(cells, "premium")
    assert doc["budget_rule"] == "premium" and doc["derived_from"]["runs"] == [RUN]
    assert {t: f["accuracy"] for t, f in doc["floors"].items()} == {
        t: f.floor for t, f in derived.per_task.items()
    }
    assert doc["latency_budget_s"] == {t: f.budget_s for t, f in derived.per_task.items()}
