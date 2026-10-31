"""Scenario switcher (SPEC §8): replay what-ifs; the controller re-picks on dev only."""

from __future__ import annotations

import pytest

from engine.eval import scenarios as S
from engine.eval.baselines import index_cells
from tests.test_o1 import cell, floors, ticket


def test_parse_cli_form():
    sc = S.parse("x", ["opus=2x"], ["haiku"], ["adjudicate=6.0"], -0.02)
    assert sc.price == {"opus": 2.0} and sc.outage == ("haiku",)
    assert sc.budget_s == {"adjudicate": 6.0} and sc.floor_delta == -0.02


def test_price_scales_costs_and_outage_removes_configs():
    t = ticket()
    cells = [cell(t, "haiku-low", latency_s=1), cell(t, "opus-low", latency_s=2)]
    out = S.apply_cells(cells, S.Scenario(name="x", price={"opus": 2.0}, outage=("haiku",)))
    assert [c.config_id for c in out] == ["opus-low"]
    assert out[0].cost_usd_nocache == pytest.approx(2 * cells[1].cost_usd_nocache)
    assert out[0].cost_usd == pytest.approx(2 * cells[1].cost_usd)


def test_budget_and_floor_overrides():
    f = S.apply_floors(floors(), S.Scenario(name="x", budget_s={"adjudicate": 6.0}, floor_delta=-0.02))
    assert (
        f.per_task["adjudicate"].budget_s == 6.0
        and f.per_task["faq"].budget_s == floors().per_task["faq"].budget_s
    )
    assert f.per_task["faq"].floor == pytest.approx(0.97)


def test_static_pick_falls_back_to_most_accurate_when_no_config_meets_the_floor():
    t = ticket()
    idx = index_cells([cell(t, "haiku-low", latency_s=1, correct=False), cell(t, "opus-low", latency_s=2)])
    assert S.pick_static(idx, floors())["adjudicate"] == "opus-low"  # only opus-low meets 0.99
    idx2 = index_cells([cell(t, "haiku-low", latency_s=1, correct=False)])
    assert S.pick_static(idx2, floors())["adjudicate"] == "haiku-low"  # none meets it: most accurate


@pytest.mark.slow
def test_no_change_reproduces_the_frozen_o1_on_dev_and_haiku_outage_drops_the_cascade():
    from engine.eval.cells import build_cells
    from engine.eval.data import load_split
    from engine.policy.cascade import run_o1
    from engine.policy.frozen import frozen_choices

    fc = frozen_choices()
    tickets = sorted(load_split("dev"), key=lambda t: t.id)
    cells, _ = build_cells([S.RUNS["dev"]], tickets)
    base = S.evaluate(fc, cells, cells, tickets, S.BASELINE)
    assert base.adapted.static == fc.static and base.adapted.o1 == fc.o1 and base.adapted.b1 == fc.b1
    frozen, _ = run_o1(tickets, index_cells(cells), fc.floors, fc.static, fc.o1)
    assert base.o1 == frozen
    out = S.evaluate(fc, cells, cells, tickets, S.Scenario(name="x", outage=("haiku",)))
    assert out.adapted.o1 is None and not any("haiku" in c for o in out.o1 for c in o.path)
